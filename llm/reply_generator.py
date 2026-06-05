from llm.groq_client import get_groq_response
from llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt


def generate_reply(
    channel: str,
    message: str,
    context_chunks: list[str],
    api_key: str,
    override_lang: str = "Auto-detect",
) -> dict:
    """
    Orchestrates retrieval → generation pipeline.

    Args:
        channel: 'telegram', 'email', or 'unknown'.
        message: Raw incoming message text.
        context_chunks: Retrieved knowledge base chunks.
        api_key: Groq API key.
        override_lang: Forced language name (optional).

    Returns:
        A dictionary containing:
        - "reply": The generated reply string.
        - "language": Info dictionary with keys code, name, flag, confidence, fallback.
    """
    user_prompt, lang_info = build_user_prompt(channel, message, context_chunks, override_lang)
    reply_text = get_groq_response(SYSTEM_PROMPT, user_prompt, api_key)
    return {
        "reply": reply_text,
        "language": lang_info,
    }
