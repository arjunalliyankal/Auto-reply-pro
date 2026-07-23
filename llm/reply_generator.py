"""
llm/reply_generator.py
──────────────────────
Full pipeline: load memory → RAG → build prompt → generate → save memory → log.
"""

from llm.groq_client import get_groq_response
from llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from llm.language_detector import detect_language
from rag.vector_store import retrieve
from memory.memory_store import get_recent_turns, get_recent_turns_by_channel, save_turn
from utils.mongo_logger import log_to_mongo


def _translate_to_english(text: str, api_key: str, model: str) -> str:
    """
    Translate any non-English text to English so the FAISS vector store
    (which is built from English documents) can do a meaningful similarity
    search.  Returns the English translation, or the original text on error.
    """
    try:
        translation = get_groq_response(
            system_prompt=(
                "You are a translation engine. "
                "Translate the following text to English. "
                "Output ONLY the English translation, nothing else."
            ),
            user_prompt=text,
            api_key=api_key,
            model=model,
        )
        return translation.strip() or text
    except Exception:
        return text


def generate_reply(
    channel:       str,
    message:       str,
    db,
    groq_api_key:  str,
    user_id:       str,
    mongo_uri:     str,
    db_name:       str,
    available_images: list = None,  # ← NEW: list of image metadata dicts
    model:         str = "llama-3.3-70b-versatile",
    memory_turns:  int = 10,
    override_lang: str = "Auto-detect",
) -> dict:
    """
    Full pipeline:
      load memory → retrieve RAG text → build prompt (with images) → generate → parse LLM attachments → save memory → log

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
    available_images : List of image metadata to pass to the LLM
    model        : Groq model identifier
    memory_turns : How many prior turns to inject into the prompt
    override_lang: Force a specific reply language (or "Auto-detect")

    Returns
    -------
    dict with keys: reply, language, model, user_id, turns_in_context, images
    """
    # 1. Load conversation history from MongoDB
    history = get_recent_turns(user_id, mongo_uri, db_name, n=memory_turns)

    # 2. RAG retrieval — translate query to English first so FAISS
    #    (built on English documents) returns meaningful chunks even
    #    when the incoming message is in Malayalam or another language.
    lang_check = detect_language(message)
    if lang_check["code"] != "en":
        retrieval_query = _translate_to_english(message, groq_api_key, model)
    else:
        retrieval_query = message
    context_chunks = retrieve(retrieval_query, db)

    # 3. Build prompt + detect language
    #    For Gmail (email) channel: also fetch any prior Telegram conversation
    #    for the same canonical_id so the LLM replies with cross-channel context.
    telegram_prior = None
    if channel == "email":
        tg_turns = get_recent_turns_by_channel(
            user_id=user_id,
            channel="telegram",
            mongo_uri=mongo_uri,
            db_name=db_name,
            n=6,
        )
        if tg_turns:
            telegram_prior = tg_turns

    prompt, lang_info = build_user_prompt(
        channel, message, context_chunks, override_lang,
        available_images=available_images,
        telegram_prior_context=telegram_prior,
    )

    # 4. Generate reply with injected memory
    reply_text = get_groq_response(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        api_key=groq_api_key,
        model=model,
        history=history,
    )

    # 5. Parse out [ATTACH: ...] tags from the LLM
    import re
    import os
    attached_files = re.findall(r'\[ATTACH:\s*(.*?)\s*\]', reply_text, flags=re.IGNORECASE)
    clean_reply_text = re.sub(r'\[ATTACH:\s*.*?\s*\]', '', reply_text, flags=re.IGNORECASE).strip()

    relevant_images = []
    if available_images and attached_files:
        for fname in attached_files:
            fname = fname.strip()
            for img in available_images:
                if os.path.basename(img["file_path"]) == fname:
                    if img not in relevant_images:
                        relevant_images.append(img)
                    break

    # Auto-attach manual uploads configured to send on first message
    if len(history) == 0 and available_images:
        for img in available_images:
            if img.get("send_on_first_message"):
                if img not in relevant_images:
                    relevant_images.append(img)

    # 6. Save this turn to MongoDB chat_memory
    save_turn(
        user_id=user_id,
        channel=channel,
        user_msg=message,
        bot_reply=clean_reply_text,
        lang_info=lang_info,
        model=model,
        mongo_uri=mongo_uri,
        db_name=db_name,
    )

    # 7. Also write to reply_logs via the existing mongo_logger (unchanged)
    log_to_mongo(
        entry={
            "user_id":      str(user_id),
            "channel":      channel,
            "message":      message,
            "reply":        clean_reply_text,
            "lang_code":    lang_info.get("code"),
            "lang_name":    lang_info.get("name"),
            "model":        model,
            "turns_used":   len(history) // 2,
            "images_sent":  len(relevant_images),
        },
        mongo_uri=mongo_uri,
        db_name=db_name,
        collection_name="reply_logs",
    )

    return {
        "reply":            clean_reply_text,
        "language":         lang_info,
        "model":            model,
        "user_id":          str(user_id),
        "turns_in_context": len(history) // 2,
        "images":           relevant_images,
    }
