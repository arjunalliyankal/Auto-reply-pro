# 🗄️ Feature: MongoDB-Backed Chat Memory

> **Integrates:** `utils/mongo_logger.py` (existing) + `feature_chat_memory.md`
> **Replaces:** `data/memory/*.jsonl` flat files with MongoDB documents
> **Result:** Per-user conversation history stored in MongoDB, queryable, persistent, and admin-manageable from Streamlit

---

## What Changes From the File-Based Memory

| Was (`.jsonl` files) | Now (MongoDB) |
|---|---|
| `data/memory/123456.jsonl` | `reply_logs` collection, filtered by `user_id` |
| One file per user on disk | One document per message turn in MongoDB |
| No querying capability | Full query: by user, channel, date, language |
| Admin clears files manually | Admin clears via Streamlit UI or Mongo query |
| Flat text, hard to analyze | Structured documents, easy to aggregate |

---

## MongoDB Document Schema

Every conversation turn writes **two documents** — one for the user message, one for the bot reply. They share a `session_id` so the full thread can be reconstructed.

```json
{
  "_id":         "ObjectId(...)",
  "user_id":     "123456789",
  "channel":     "telegram",
  "role":        "user",
  "content":     "Tell me about the Full Stack course",
  "lang_code":   "en",
  "lang_name":   "English",
  "session_id":  "123456789_20260611",
  "turn_index":  1,
  "created_at":  "2026-06-11T09:10:00Z"
}
```

```json
{
  "_id":         "ObjectId(...)",
  "user_id":     "123456789",
  "channel":     "telegram",
  "role":        "assistant",
  "content":     "Our Full Stack Web Development course is 6 months...",
  "lang_code":   "en",
  "lang_name":   "English",
  "model":       "llama-3.3-70b-versatile",
  "session_id":  "123456789_20260611",
  "turn_index":  1,
  "created_at":  "2026-06-11T09:10:02Z"
}
```

---

## Updated File: `memory/memory_store.py`

Replace the entire file-based implementation with this MongoDB version. The public API (`get_recent_turns`, `save_turn`, `clear_history`) stays **identical** — so `reply_generator.py` needs no changes beyond passing `mongo_uri` and `db_name`.

```python
"""
memory/memory_store.py
──────────────────────
MongoDB-backed per-user conversation memory.
Replaces the flat .jsonl file store with pymongo documents.

Public API (same as the file-based version):
  get_recent_turns(user_id, n, mongo_uri, db_name) -> list[dict]
  save_turn(user_id, channel, user_msg, bot_reply, lang_info, model, mongo_uri, db_name)
  clear_history(user_id, mongo_uri, db_name)
  get_all_users(mongo_uri, db_name) -> list[str]
  load_history(user_id, mongo_uri, db_name) -> list[dict]
"""

import logging
from datetime import datetime, timezone, date

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
from typing import Optional

logger = logging.getLogger(__name__)

# ── Module-level cached client ────────────────────────────────────────────────
_client: Optional[MongoClient]  = None
_db_ref                         = None

COLLECTION_NAME = "chat_memory"


# ── Connection (reuses mongo_logger pattern) ──────────────────────────────────

def _get_collection(mongo_uri: str, db_name: str):
    """
    Return a cached pymongo Collection for chat_memory.
    Safe to call repeatedly — creates the connection only once.
    Also ensures the required index exists on first call.
    """
    global _client, _db_ref

    if _db_ref is None:
        try:
            _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            _client.admin.command("ping")
            _db_ref = _client[db_name]
            # Create index on user_id + created_at for fast per-user queries
            _db_ref[COLLECTION_NAME].create_index(
                [("user_id", ASCENDING), ("created_at", ASCENDING)],
                name="user_id_created_at"
            )
            logger.info("✅ chat_memory connected to MongoDB: %s / %s", mongo_uri, db_name)
        except (ConnectionFailure, OperationFailure) as exc:
            logger.warning("⚠️  chat_memory MongoDB connection failed: %s", exc)
            _db_ref = None

    return _db_ref[COLLECTION_NAME] if _db_ref is not None else None


def _session_id(user_id: str) -> str:
    """Daily session ID — groups messages from the same user on the same day."""
    return f"{user_id}_{date.today().isoformat()}"


# ── Public API ────────────────────────────────────────────────────────────────

def save_turn(
    user_id:    str,
    channel:    str,
    user_msg:   str,
    bot_reply:  str,
    lang_info:  dict,
    model:      str,
    mongo_uri:  str,
    db_name:    str,
) -> bool:
    """
    Persist one conversation turn (user message + bot reply) as two
    documents in the chat_memory collection, linked by session_id.

    Parameters
    ----------
    user_id   : Telegram chat_id (str) or sender email address
    channel   : "telegram" | "email" | "unknown"
    user_msg  : Raw incoming message text
    bot_reply : Generated reply text
    lang_info : Dict from language_detector — {"code","name","flag",...}
    model     : Groq model string used for this reply
    mongo_uri : MongoDB connection URI
    db_name   : Target database name

    Returns True on success, False on any error.
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        logger.warning("⚠️  save_turn skipped – no MongoDB connection.")
        return False

    # Resolve next turn index for this user
    last = coll.find_one(
        {"user_id": user_id},
        sort=[("turn_index", -1)],
        projection={"turn_index": 1}
    )
    turn_index = (last["turn_index"] + 1) if last else 1

    now        = datetime.now(timezone.utc)
    session_id = _session_id(user_id)

    base = {
        "user_id":    str(user_id),
        "channel":    channel,
        "lang_code":  lang_info.get("code", "en"),
        "lang_name":  lang_info.get("name", "English"),
        "session_id": session_id,
        "turn_index": turn_index,
        "created_at": now,
    }

    try:
        coll.insert_many([
            {**base, "role": "user",      "content": user_msg[:2000]},
            {**base, "role": "assistant", "content": bot_reply[:2000], "model": model},
        ])
        return True
    except Exception as exc:
        logger.warning("⚠️  save_turn insert error: %s", exc)
        return False


def get_recent_turns(
    user_id:   str,
    mongo_uri: str,
    db_name:   str,
    n:         int = 6,
) -> list[dict]:
    """
    Fetch the last n complete turns (n user + n assistant messages = 2n docs)
    for a user, sorted oldest-first so the LLM sees them in correct order.

    Returns a list of OpenAI/Groq-compatible message dicts:
    [{"role": "user"|"assistant", "content": "..."}]
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return []

    # Find distinct turn indices, descending, take last n turns
    pipeline = [
        {"$match": {"user_id": str(user_id)}},
        {"$sort":  {"turn_index": -1}},
        {"$group": {"_id": "$turn_index"}},
        {"$limit": n},
        {"$sort":  {"_id": 1}},     # re-sort ascending for prompt order
    ]
    recent_indices = [doc["_id"] for doc in coll.aggregate(pipeline)]

    if not recent_indices:
        return []

    docs = list(
        coll.find(
            {"user_id": str(user_id), "turn_index": {"$in": recent_indices}},
            sort=[("turn_index", ASCENDING), ("role", ASCENDING)],
            projection={"role": 1, "content": 1, "_id": 0}
        )
    )

    # Ensure correct order within each turn: user before assistant
    ordered = []
    turns: dict[int, dict] = {}
    for doc in coll.find(
        {"user_id": str(user_id), "turn_index": {"$in": recent_indices}},
        sort=[("turn_index", ASCENDING)],
    ):
        ti = doc["turn_index"]
        if ti not in turns:
            turns[ti] = {"user": None, "assistant": None}
        turns[ti][doc["role"]] = doc["content"]

    for ti in sorted(turns.keys()):
        if turns[ti]["user"]:
            ordered.append({"role": "user",      "content": turns[ti]["user"]})
        if turns[ti]["assistant"]:
            ordered.append({"role": "assistant", "content": turns[ti]["assistant"]})

    return ordered


def load_history(
    user_id:   str,
    mongo_uri: str,
    db_name:   str,
) -> list[dict]:
    """
    Load full conversation history for a user (all turns, all time).
    Used by the Streamlit Memory Manager for display purposes.
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return []

    return list(
        coll.find(
            {"user_id": str(user_id)},
            sort=[("turn_index", ASCENDING), ("role", ASCENDING)],
            projection={"role": 1, "content": 1, "lang_name": 1,
                        "channel": 1, "created_at": 1, "turn_index": 1, "_id": 0}
        )
    )


def clear_history(user_id: str, mongo_uri: str, db_name: str) -> int:
    """
    Delete all memory documents for a user.
    Returns the number of documents deleted.
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return 0
    result = coll.delete_many({"user_id": str(user_id)})
    logger.info("Cleared %d memory docs for user %s", result.deleted_count, user_id)
    return result.deleted_count


def get_all_users(mongo_uri: str, db_name: str) -> list[dict]:
    """
    Return a summary list of all users with stored memory.
    Each entry: {"user_id", "channel", "turn_count", "last_seen"}
    """
    coll = _get_collection(mongo_uri, db_name)
    if coll is None:
        return []

    pipeline = [
        {"$group": {
            "_id":        "$user_id",
            "channel":    {"$first": "$channel"},
            "turn_count": {"$sum": 1},
            "last_seen":  {"$max": "$created_at"},
        }},
        {"$sort": {"last_seen": -1}},
    ]
    return [
        {
            "user_id":    doc["_id"],
            "channel":    doc.get("channel", "unknown"),
            "turn_count": doc["turn_count"] // 2,   # messages → turns
            "last_seen":  doc["last_seen"],
        }
        for doc in coll.aggregate(pipeline)
    ]
```

---

## Updated File: `llm/reply_generator.py`

Pass `mongo_uri` and `db_name` through to memory functions.

```python
from llm.groq_client import get_groq_response
from llm.prompt_builder import build_user_prompt, SYSTEM_PROMPT
from rag.vector_store import retrieve
from memory.memory_store import get_recent_turns, save_turn
from utils.mongo_logger import log_to_mongo     # existing logger — unchanged

def generate_reply(
    channel:       str,
    message:       str,
    db,
    groq_api_key:  str,
    user_id:       str,
    mongo_uri:     str,
    db_name:       str,
    model:         str = "llama-3.3-70b-versatile",
    memory_turns:  int = 6,
) -> dict:
    """
    Full pipeline:
      load memory → retrieve RAG → build prompt → generate → save memory → log

    Both chat_memory (per-user history) and reply_logs (audit log) are
    written to the same MongoDB instance via their respective functions.
    """
    # 1. Load conversation history from MongoDB
    history = get_recent_turns(user_id, mongo_uri, db_name, n=memory_turns)

    # 2. RAG retrieval
    context_chunks = retrieve(message, db)

    # 3. Build prompt + detect language
    prompt, lang_info = build_user_prompt(channel, message, context_chunks)

    # 4. Generate reply with injected memory
    reply_text = get_groq_response(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        api_key=groq_api_key,
        model=model,
        history=history,
    )

    # 5. Save this turn to MongoDB chat_memory
    save_turn(
        user_id=user_id,
        channel=channel,
        user_msg=message,
        bot_reply=reply_text,
        lang_info=lang_info,
        model=model,
        mongo_uri=mongo_uri,
        db_name=db_name,
    )

    # 6. Also write to reply_logs via the existing mongo_logger (unchanged)
    log_to_mongo(
        entry={
            "user_id":    user_id,
            "channel":    channel,
            "message":    message,
            "reply":      reply_text,
            "lang_code":  lang_info.get("code"),
            "lang_name":  lang_info.get("lang_name"),
            "model":      model,
            "turns_used": len(history) // 2,
        },
        mongo_uri=mongo_uri,
        db_name=db_name,
        collection_name="reply_logs",   # existing collection — untouched
    )

    return {
        "reply":            reply_text,
        "language":         lang_info,
        "model":            model,
        "user_id":          str(user_id),
        "turns_in_context": len(history) // 2,
    }
```

---

## Updated: Streamlit Sidebar — MongoDB Config

```python
with st.sidebar:
    st.subheader("🗄️ MongoDB")
    mongo_uri = st.text_input(
        "MongoDB URI",
        value="mongodb://localhost:27017",
        help="Local: mongodb://localhost:27017 · Atlas: mongodb+srv://..."
    )
    db_name = st.text_input("Database Name", value="autoreply_pro")

    # Connection status indicator
    if st.button("🔌 Test Connection"):
        try:
            from pymongo import MongoClient
            c = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            c.admin.command("ping")
            st.success("✅ MongoDB connected")
        except Exception as e:
            st.error(f"❌ {e}")
```

---

## Updated: Streamlit Memory Manager Tab

```python
with tab2:
    st.header("🧠 Memory Manager")

    from memory.memory_store import get_all_users, load_history, clear_history

    users = get_all_users(mongo_uri, db_name)

    if not users:
        st.info("No conversation memory stored yet.")
    else:
        st.write(f"**{len(users)} user(s) with stored memory**")

        # Summary table
        import pandas as pd
        df = pd.DataFrame(users)
        df["last_seen"] = pd.to_datetime(df["last_seen"]).dt.strftime("%Y-%m-%d %H:%M UTC")
        st.dataframe(df, use_container_width=True)

        st.divider()
        selected_user = st.selectbox(
            "Inspect user conversation",
            options=[u["user_id"] for u in users],
            format_func=lambda uid: f"{uid} ({next(u['channel'] for u in users if u['user_id']==uid)})"
        )

        if selected_user:
            history = load_history(selected_user, mongo_uri, db_name)
            turns   = [history[i:i+2] for i in range(0, len(history), 2)]

            for i, turn in enumerate(turns):
                user_msg = turn[0]["content"] if len(turn) > 0 else ""
                bot_msg  = turn[1]["content"] if len(turn) > 1 else ""
                lang     = turn[0].get("lang_name", "")
                ts       = turn[0].get("created_at", "")
                with st.expander(f"Turn {i+1} · {lang} · {str(ts)[:16]} — {user_msg[:55]}..."):
                    col1, col2 = st.columns(2)
                    col1.markdown(f"**👤 User**\n\n{user_msg}")
                    col2.markdown(f"**🤖 Bot**\n\n{bot_msg}")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button(f"🗑️ Clear {selected_user}", type="secondary"):
                    n = clear_history(selected_user, mongo_uri, db_name)
                    st.success(f"Deleted {n} documents.")
                    st.rerun()
            with col_b:
                if st.button("🗑️ Clear ALL users", type="primary"):
                    for u in users:
                        clear_history(u["user_id"], mongo_uri, db_name)
                    st.success("All memory cleared.")
                    st.rerun()
```

---

## MongoDB Collections Overview

Two collections in the same database — separate concerns, same connection.

```
autoreply_pro (database)
│
├── reply_logs          ← managed by utils/mongo_logger.py (EXISTING, unchanged)
│   every outgoing reply, one doc per reply, audit trail
│
└── chat_memory         ← managed by memory/memory_store.py (NEW)
    per-user conversation turns, two docs per turn (user + assistant)
    indexed on (user_id, created_at) for fast per-user queries
```

### Useful Queries (MongoDB Shell / Compass)

```javascript
// All turns for a specific Telegram user
db.chat_memory.find({ user_id: "123456789" }).sort({ turn_index: 1 })

// All turns for an email user
db.chat_memory.find({ user_id: "customer@gmail.com" }).sort({ created_at: 1 })

// Count turns per user
db.chat_memory.aggregate([
  { $group: { _id: "$user_id", turns: { $sum: 1 } } },
  { $sort: { turns: -1 } }
])

// All Malayalam conversations
db.chat_memory.find({ lang_code: "ml" })

// Delete one user's memory
db.chat_memory.deleteMany({ user_id: "123456789" })

// Today's conversations
db.chat_memory.find({
  created_at: { $gte: new Date(new Date().setHours(0,0,0,0)) }
})
```

---

## `.env.example` Addition

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=autoreply_pro
```

---

## Files Changed Summary

```
autoreply_pro/
│
├── utils/
│   └── mongo_logger.py          ← UNCHANGED (still logs to reply_logs)
│
├── memory/
│   └── memory_store.py          ← REPLACED (file-based → MongoDB)
│
├── llm/
│   └── reply_generator.py       ← UPDATED (passes mongo_uri + db_name)
│
└── app.py                       ← UPDATED (MongoDB sidebar config + Memory Manager tab)
```

---

## No New Dependencies

`utils/mongo_logger.py` already pulls in `pymongo`. `memory/memory_store.py` uses the same import. Nothing to add to `requirements.txt`.