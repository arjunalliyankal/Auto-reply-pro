"""
memory/identity_store.py
────────────────────────
Manages the user_identity collection.

Responsibilities:
  - Resolve any channel-specific ID (telegram_id, whatsapp_id, email) to a
    single canonical_id (always the email address).
  - Store and retrieve telegram_id / whatsapp_id ↔ email links.
  - Detect whether a new Telegram user still needs to be asked
    for their email (pending_link state).
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
            _collection.create_index("telegram_id",   name="telegram_id_idx",   sparse=True)
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
