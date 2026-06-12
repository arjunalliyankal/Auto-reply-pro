"""
utils/mongo_logger.py
─────────────────────
Thin wrapper around pymongo to persist reply-log entries to a local
MongoDB database.  Import `log_to_mongo` and call it with any log
entry dict; the function is safe to call even if MongoDB is not
reachable (it logs a warning and returns False instead of raising).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

# ── Module-level cached client/collection ─────────────────────────────────────
_client: Optional[MongoClient] = None
_collection = None


def _get_collection(mongo_uri: str, db_name: str, collection_name: str = "reply_logs"):
    """Return a cached pymongo Collection, creating the connection on first call."""
    global _client, _collection

    if _collection is None:
        try:
            _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            # Force an actual connection attempt
            _client.admin.command("ping")
            db = _client[db_name]
            _collection = db[collection_name]
            logger.info("✅ Connected to MongoDB: %s / %s / %s", mongo_uri, db_name, collection_name)
        except (ConnectionFailure, OperationFailure) as exc:
            logger.warning("⚠️  MongoDB connection failed: %s", exc)
            _collection = None

    return _collection


def log_to_mongo(entry: dict, mongo_uri: str, db_name: str, collection_name: str = "reply_logs") -> bool:
    """
    Insert a single reply-log entry into MongoDB.

    Parameters
    ----------
    entry          : dict   – the log record (channel, message, reply, ts, …)
    mongo_uri      : str    – e.g. "mongodb://localhost:27017"
    db_name        : str    – e.g. "autoreply_pro"
    collection_name: str    – defaults to "reply_logs"

    Returns
    -------
    True on success, False on any error.
    """
    coll = _get_collection(mongo_uri, db_name, collection_name)
    if coll is None:
        logger.warning("⚠️  Skipping MongoDB insert – no active connection.")
        return False

    try:
        # Add a proper ISO datetime alongside the raw Unix timestamp
        doc = dict(entry)
        doc.setdefault("created_at", datetime.now(timezone.utc))
        result = coll.insert_one(doc)
        logger.debug("Inserted log with _id=%s", result.inserted_id)
        return True
    except Exception as exc:
        logger.warning("⚠️  MongoDB insert error: %s", exc)
        return False


def reset_connection() -> None:
    """Drop the cached connection (useful for testing or re-connecting)."""
    global _client, _collection
    if _client:
        _client.close()
    _client = None
    _collection = None
