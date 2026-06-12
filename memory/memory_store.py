"""
memory/memory_store.py
──────────────────────
MongoDB-backed per-user conversation memory.
Replaces the flat .jsonl file store with pymongo documents.

Public API:
  get_recent_turns(user_id, mongo_uri, db_name, n) -> list[dict]
  save_turn(user_id, channel, user_msg, bot_reply, lang_info, model, mongo_uri, db_name)
"""

import logging
from datetime import datetime, timezone, date
from typing import Optional

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

# ── Module-level cached client ────────────────────────────────────────────────
_client: Optional[MongoClient] = None
_db_ref = None

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
    user_id:   str,
    channel:   str,
    user_msg:  str,
    bot_reply: str,
    lang_info: dict,
    model:     str,
    mongo_uri: str,
    db_name:   str,
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
        {"user_id": str(user_id)},
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

    # Reconstruct ordered user/assistant pairs per turn
    turns: dict[int, dict] = {}
    for doc in coll.find(
        {"user_id": str(user_id), "turn_index": {"$in": recent_indices}},
        sort=[("turn_index", ASCENDING)],
    ):
        ti = doc["turn_index"]
        if ti not in turns:
            turns[ti] = {"user": None, "assistant": None}
        turns[ti][doc["role"]] = doc["content"]

    ordered = []
    for ti in sorted(turns.keys()):
        if turns[ti]["user"]:
            ordered.append({"role": "user",      "content": turns[ti]["user"]})
        if turns[ti]["assistant"]:
            ordered.append({"role": "assistant", "content": turns[ti]["assistant"]})

    return ordered


