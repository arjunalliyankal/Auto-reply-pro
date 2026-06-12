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
    "👋 Welcome! I'm your assistant.\n"
    "please reply with your *email address to Continue*."
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
