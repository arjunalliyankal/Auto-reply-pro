"""
llm/reply_generator.py
──────────────────────
Full pipeline: load memory → RAG → build prompt → generate → save memory → log.
"""

from llm.groq_client import get_groq_response
from llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from rag.vector_store import retrieve
from memory.memory_store import get_recent_turns, save_turn
from utils.mongo_logger import log_to_mongo


def generate_reply(
    channel:      str,
    message:      str,
    db,
    groq_api_key: str,
    user_id:      str,
    mongo_uri:    str,
    db_name:      str,
    model:        str = "llama-3.3-70b-versatile",
    memory_turns: int = 6,
    override_lang: str = "Auto-detect",
) -> dict:
    """
    Full pipeline:
      load memory → retrieve RAG → build prompt → generate → save memory → log

    Both chat_memory (per-user history) and reply_logs (audit log) are
    written to the same MongoDB instance via their respective functions.

    Parameters
    ----------
    channel      : "telegram" | "email" | "unknown"
    message      : Raw incoming message text
    db           : FAISS vector store (from rag.vector_store.load_index)
    groq_api_key : Groq API key
    user_id      : Telegram chat_id (str) or sender email address
    mongo_uri    : MongoDB connection URI
    db_name      : Target database name
    model        : Groq model identifier
    memory_turns : How many prior turns to inject into the prompt
    override_lang: Force a specific reply language (or "Auto-detect")

    Returns
    -------
    dict with keys: reply, language, model, user_id, turns_in_context
    """
    # 1. Load conversation history from MongoDB
    history = get_recent_turns(user_id, mongo_uri, db_name, n=memory_turns)

    # 2. RAG retrieval
    context_chunks = retrieve(message, db)

    # 3. Build prompt + detect language
    prompt, lang_info = build_user_prompt(channel, message, context_chunks, override_lang)

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
            "user_id":    str(user_id),
            "channel":    channel,
            "message":    message,
            "reply":      reply_text,
            "lang_code":  lang_info.get("code"),
            "lang_name":  lang_info.get("name"),
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
