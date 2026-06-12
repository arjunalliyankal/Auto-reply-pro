# 🔗 Feature: Cross-Channel Identity — Unified Memory via Email Linking

> **Add-on to:** `feature_mongo_memory.md`
> **Strategy:** On first Telegram message, bot asks for email. Once provided, a `user_identity` document links `telegram_id ↔ email`. All memory is stored and retrieved under one canonical `user_id` (the email) regardless of which channel the message arrives on.

---

## How It Works

```
First Telegram message from new user
         │
         ▼
Check user_identity collection
  → No record found for this chat_id
         │
         ▼
Bot replies:
  "👋 Welcome! To personalise your experience,
   please share your email address."
         │
         ▼
User replies with email
         │
         ▼
Validate email format
         │
         ▼
Save to user_identity:
  { telegram_id: "123456789",
    email: "customer@gmail.com",
    canonical_id: "customer@gmail.com" }
         │
         ▼
All future messages (Telegram + Gmail)
resolve to canonical_id = "customer@gmail.com"
         │
         ▼
chat_memory always keyed on canonical_id ✅
reply_logs always keyed on canonical_id ✅
```

---

## New MongoDB Collection: `user_identity`

One document per linked user.

```json
{
  "_id":          "ObjectId(...)",
  "canonical_id": "customer@gmail.com",
  "email":        "customer@gmail.com",
  "telegram_id":  "123456789",
  "linked_at":    "2026-06-11T09:10:00Z",
  "channels":     ["telegram", "email"],
  "verified":     true
}
```

### Collections Overview (updated)

```
autoreply_pro (database)
│
├── reply_logs       ← audit log, keyed on canonical_id
├── chat_memory      ← conversation turns, keyed on canonical_id
└── user_identity    ← NEW: telegram_id ↔ email mapping
```

---

## New File: `memory/identity_store.py`

```python
"""
memory/identity_store.py
────────────────────────
Manages the user_identity collection.

Responsibilities:
  - Resolve any channel-specific ID (telegram_id, email) to a
    single canonical_id (always the email address).
  - Store and retrieve telegram_id ↔ email links.
  - Detect whether a new Telegram user still needs to be asked for
    their email (pending_link state).
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

COLLECTION_NAME = "user_identity"

# Module-level cached collection
_client     = None
_collection = None

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")


# ── Connection ────────────────────────────────────────────────────────────────

def _get_collection(mongo_uri: str, db_name: str):
    global _client, _collection

    if _collection is None:
        try:
            _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            _client.admin.command("ping")
            db = _client[db_name]
            _collection = db[COLLECTION_NAME]

            # Indexes for fast lookup in both directions
            _collection.create_index("canonical_id",  name="canonical_id_idx")
            _collection.create_index("telegram_id",   name="telegram_id_idx",  sparse=True)
            _collection.create_index("email",          name="email_idx",         unique=True, sparse=True)

            logger.info("✅ user_identity connected: %s / %s", mongo_uri, db_name)
        except (ConnectionFailure, OperationFailure) as exc:
            logger.warning("⚠️  user_identity MongoDB failed: %s", exc)
            _collection = None

    return _collection


# ── Core Resolution ───────────────────────────────────────────────────────────

def resolve_canonical_id(
    channel:     str,
    raw_id:      str,
    mongo_uri:   str,
    db_name:     str,
) -> Optional[str]:
    """
    Return the canonical_id (email) for a given channel + raw_id.

    Returns:
        str   → the canonical_id (email) if the user is fully linked
        None  → user is not yet linked (need to ask for email)
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        # Fallback: use raw_id as canonical (degraded mode)
        return raw_id

    if channel == "email":
        # Email is already canonical — upsert identity if missing
        doc = coll.find_one({"email": raw_id})
        if not doc:
            _upsert_email_only(raw_id, coll)
        return raw_id

    elif channel == "telegram":
        doc = coll.find_one({"telegram_id": str(raw_id)})
        if doc:
            return doc["canonical_id"]
        return None     # ← triggers onboarding flow

    else:
        return raw_id   # unknown channel — use as-is


def _upsert_email_only(email: str, coll) -> None:
    """Create a minimal identity record for an email-only user."""
    coll.update_one(
        {"email": email},
        {"$setOnInsert": {
            "canonical_id": email,
            "email":        email,
            "telegram_id":  None,
            "linked_at":    datetime.now(timezone.utc),
            "channels":     ["email"],
            "verified":     True,
        }},
        upsert=True
    )


# ── Linking ───────────────────────────────────────────────────────────────────

def is_valid_email(text: str) -> bool:
    """Basic email format check."""
    return bool(EMAIL_REGEX.match(text.strip()))


def link_telegram_to_email(
    telegram_id: str,
    email:       str,
    mongo_uri:   str,
    db_name:     str,
) -> dict:
    """
    Link a Telegram chat_id to an email address.

    Handles three cases:
    1. Email is brand new              → create fresh identity
    2. Email already exists (email-only user) → attach telegram_id to it
    3. telegram_id already linked elsewhere → return error

    Returns:
        {"success": True,  "canonical_id": "...", "case": "new"|"merged"}
        {"success": False, "reason": "already_linked"|"invalid_email"|"db_error"}
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return {"success": False, "reason": "db_error"}

    email = email.strip().lower()

    if not is_valid_email(email):
        return {"success": False, "reason": "invalid_email"}

    # Check if this telegram_id is already linked to a different email
    existing_tg = coll.find_one({"telegram_id": str(telegram_id)})
    if existing_tg:
        return {
            "success":      True,
            "canonical_id": existing_tg["canonical_id"],
            "case":         "already_linked",
        }

    # Check if email already has a record (email-only user)
    existing_email = coll.find_one({"email": email})

    now = datetime.now(timezone.utc)

    if existing_email:
        # Merge: attach telegram_id to the existing email identity
        coll.update_one(
            {"email": email},
            {"$set": {
                "telegram_id": str(telegram_id),
                "linked_at":   now,
            },
            "$addToSet": {"channels": "telegram"}}
        )
        return {"success": True, "canonical_id": email, "case": "merged"}

    else:
        # New user: create full identity
        coll.insert_one({
            "canonical_id": email,
            "email":        email,
            "telegram_id":  str(telegram_id),
            "linked_at":    now,
            "channels":     ["telegram"],
            "verified":     True,
        })
        return {"success": True, "canonical_id": email, "case": "new"}


def get_identity(canonical_id: str, mongo_uri: str, db_name: str) -> Optional[dict]:
    """Fetch full identity document by canonical_id."""
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return None
    return coll.find_one({"canonical_id": canonical_id}, projection={"_id": 0})


def get_all_identities(mongo_uri: str, db_name: str) -> list[dict]:
    """Return all identity records — used by Streamlit Identity Manager."""
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return []
    return list(coll.find({}, projection={"_id": 0}, sort=[("linked_at", -1)]))


# ── Pending State (in-memory, per process) ────────────────────────────────────
# Tracks Telegram users who have been asked for their email but haven't replied yet.

_pending_email_request: set[str] = set()


def mark_pending(telegram_id: str) -> None:
    """Mark a Telegram user as waiting for their email input."""
    _pending_email_request.add(str(telegram_id))


def is_pending(telegram_id: str) -> bool:
    """Return True if we're waiting for this user to send their email."""
    return str(telegram_id) in _pending_email_request


def clear_pending(telegram_id: str) -> None:
    """Remove pending state once email is received and linked."""
    _pending_email_request.discard(str(telegram_id))
```

---

## New File: `memory/onboarding.py`

Handles the Telegram onboarding conversation — asking for email, validating, linking.

```python
"""
memory/onboarding.py
────────────────────
Manages the one-time email-collection flow for new Telegram users.

Flow:
  1. New user detected (no identity record)       → send welcome + ask email
  2. User replies with text while pending          → validate + link
  3. Success                                       → confirm + continue normally
  4. Invalid email                                 → ask again (max 3 attempts)
"""

from memory.identity_store import (
    is_valid_email, link_telegram_to_email,
    mark_pending, is_pending, clear_pending,
)

# Track failed attempts per telegram_id (in-memory)
_attempts: dict[str, int] = {}
MAX_ATTEMPTS = 3

WELCOME_MESSAGE = (
    "👋 Welcome! I'm the EduReach Academy assistant.\n\n"
    "To remember your conversation history across all channels, "
    "please reply with your *email address*."
)

INVALID_EMAIL_MESSAGE = (
    "⚠️ That doesn't look like a valid email address. "
    "Please try again (e.g. yourname@gmail.com)."
)

MAX_ATTEMPTS_MESSAGE = (
    "No problem! You can continue without linking. "
    "Type your question anytime and I'll help you. 😊"
)

SUCCESS_MESSAGE = (
    "✅ Got it! Your account is now linked. "
    "I'll remember your conversations whether you message me here or by email. "
    "How can I help you today?"
)

ALREADY_LINKED_MESSAGE = (
    "✅ Your account is already linked. How can I help you today?"
)


def handle_onboarding(
    telegram_id: str,
    text:        str,
    mongo_uri:   str,
    db_name:     str,
) -> dict:
    """
    Drive the onboarding state machine for a Telegram user.

    Returns:
    {
      "status":   "ask_email"      → send WELCOME_MESSAGE, do not process as normal reply
                  "waiting"        → invalid email, send retry message
                  "success"        → linked, send SUCCESS_MESSAGE, then process normally
                  "skipped"        → max attempts reached, proceed without linking
                  "already_linked" → user already linked, proceed normally
      "reply":    str              → message to send back to user
      "canonical_id": str | None  → set when status is "success"
    }
    """
    tid = str(telegram_id)

    # Already waiting for email input
    if is_pending(tid):
        attempts = _attempts.get(tid, 0) + 1
        _attempts[tid] = attempts

        if not is_valid_email(text):
            if attempts >= MAX_ATTEMPTS:
                clear_pending(tid)
                _attempts.pop(tid, None)
                return {"status": "skipped", "reply": MAX_ATTEMPTS_MESSAGE, "canonical_id": None}
            return {"status": "waiting", "reply": INVALID_EMAIL_MESSAGE, "canonical_id": None}

        # Valid email — link it
        result = link_telegram_to_email(tid, text, mongo_uri, db_name)
        clear_pending(tid)
        _attempts.pop(tid, None)

        if result["success"]:
            if result["case"] == "already_linked":
                return {"status": "already_linked", "reply": ALREADY_LINKED_MESSAGE,
                        "canonical_id": result["canonical_id"]}
            return {"status": "success", "reply": SUCCESS_MESSAGE,
                    "canonical_id": result["canonical_id"]}
        else:
            return {"status": "waiting", "reply": INVALID_EMAIL_MESSAGE, "canonical_id": None}

    # New user — ask for email
    mark_pending(tid)
    _attempts[tid] = 0
    return {"status": "ask_email", "reply": WELCOME_MESSAGE, "canonical_id": None}
```

---

## Updated: Telegram Automation Loop in `app.py`

```python
from memory.identity_store import resolve_canonical_id
from memory.onboarding import handle_onboarding

# Inside the Telegram polling loop:
for update in tg.get_updates():
    parsed = tg.parse_message(update)
    if not parsed:
        continue

    chat_id, msg_text = parsed
    tid = str(chat_id)

    # Handle reset command
    if is_reset_command(msg_text):
        clear_history(tid, mongo_uri, db_name)
        tg.send_reply(chat_id, "✅ Conversation history cleared. Starting fresh!")
        continue

    # Resolve canonical_id
    canonical_id = resolve_canonical_id("telegram", tid, mongo_uri, db_name)

    if canonical_id is None:
        # New or pending user — run onboarding
        ob = handle_onboarding(tid, msg_text, mongo_uri, db_name)
        tg.send_reply(chat_id, ob["reply"])

        if ob["status"] in ("ask_email", "waiting", "skipped"):
            # Don't process as a business query yet
            if ob["status"] == "skipped":
                # Use telegram_id as fallback canonical_id
                canonical_id = tid
            else:
                continue

        elif ob["status"] in ("success", "already_linked"):
            canonical_id = ob["canonical_id"]
            # After linking, if they sent a real question alongside email,
            # it was the email itself — skip processing, wait for next message
            continue

    # Normal reply generation with unified canonical_id
    result = generate_reply(
        channel="telegram",
        message=msg_text,
        db=db,
        groq_api_key=groq_key,
        user_id=canonical_id,       # ← always canonical (email)
        mongo_uri=mongo_uri,
        db_name=db_name,
        model=groq_model,
    )
    tg.send_reply(chat_id, result["reply"])
```

---

## Gmail Loop — No Changes Needed

Gmail already uses the sender's email as `user_id`, which is already the `canonical_id`. The identity store auto-creates an email-only record on first contact.

```python
# Gmail loop stays the same — email IS the canonical_id
result = generate_reply(
    channel="email",
    message=body,
    db=db,
    groq_api_key=groq_key,
    user_id=to_addr,            # ← email address, already canonical
    mongo_uri=mongo_uri,
    db_name=db_name,
    model=groq_model,
)
```

---

## Streamlit Identity Manager Tab

Add a fourth tab to `app.py`.

```python
tab1, tab2, tab3, tab4 = st.tabs([
    "📨 Live Log", "🧠 Memory Manager", "📊 Stats", "🔗 Identity Manager"
])

with tab4:
    st.header("🔗 Cross-Channel Identity Manager")

    from memory.identity_store import get_all_identities

    identities = get_all_identities(mongo_uri, db_name)

    if not identities:
        st.info("No linked identities yet.")
    else:
        import pandas as pd
        df = pd.DataFrame(identities)
        df["linked_at"] = pd.to_datetime(df["linked_at"]).dt.strftime("%Y-%m-%d %H:%M")
        df["telegram_linked"] = df["telegram_id"].notna()
        df["email_linked"]    = df["email"].notna()
        st.dataframe(
            df[["canonical_id", "telegram_id", "telegram_linked", "email_linked", "channels", "linked_at"]],
            use_container_width=True
        )
        st.caption(f"{len(df)} total users · "
                   f"{df['telegram_linked'].sum()} Telegram-linked · "
                   f"{df['email_linked'].sum()} email-linked")
```

---

## End-to-End Scenario

```
Day 1 — Customer messages on Telegram
──────────────────────────────────────
User (Telegram):   "Hello"
Bot:               "👋 Welcome! Please reply with your email address."
User (Telegram):   "rahul@gmail.com"
Bot:               "✅ Account linked! How can I help you today?"
User (Telegram):   "Tell me about the Full Stack course"
Bot:               [RAG reply about Full Stack]
User (Telegram):   "What is the fee?"
Bot:               "The fee is ₹24,999..."   ← memory working ✅

Day 2 — Same customer emails from rahul@gmail.com
──────────────────────────────────────────────────
User (Email):      "Do you have EMI options?"
Bot:               "Yes! For the Full Stack course you asked about,
                    EMI is available as ₹8,500/month for 3 months."
                   ← remembers Telegram conversation ✅
                   ← unified memory under rahul@gmail.com ✅
```

---

## Files Added / Changed Summary

```
autoreply_pro/
│
├── memory/
│   ├── memory_store.py        ← UNCHANGED from mongo_memory spec
│   ├── identity_store.py      ← NEW — telegram↔email linking + resolution
│   └── onboarding.py          ← NEW — Telegram email-collection flow
│
└── app.py                     ← UPDATED — onboarding in Telegram loop
                                           + Identity Manager tab
```

No new dependencies — uses only `pymongo` (already installed) and Python stdlib `re`.