from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Fix random seed so detection is deterministic
DetectorFactory.seed = 42

# ── Supported languages (English + Malayalam only) ────────────────────────────
LANGUAGE_NAMES = {
    "en": "English",
    "ml": "Malayalam",
}

# Language code → flag emoji
LANGUAGE_FLAGS = {
    "en": "🇬🇧",
    "ml": "🇮🇳",
}

SUPPORTED_CODES = set(LANGUAGE_NAMES.keys())

DEFAULT_LANGUAGE_CODE = "en"
DEFAULT_LANGUAGE_NAME = "English"
MIN_TEXT_LENGTH = 10   # Skip detection for very short inputs


def detect_language(text: str) -> dict:
    """
    Detect the language of an input string.
    Only English and Malayalam are supported; any other detected language
    falls back to English.

    Returns a dict:
    {
        "code":       "ml",
        "name":       "Malayalam",
        "flag":       "🇮🇳",
        "confidence": "high" | "low",
        "fallback":   False
    }
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return {
            "code":       DEFAULT_LANGUAGE_CODE,
            "name":       DEFAULT_LANGUAGE_NAME,
            "flag":       LANGUAGE_FLAGS[DEFAULT_LANGUAGE_CODE],
            "confidence": "low",
            "fallback":   True,
        }

    try:
        code = detect(text.strip())

        # If the detected language is not in our supported set, fall back to English
        if code not in SUPPORTED_CODES:
            return {
                "code":       DEFAULT_LANGUAGE_CODE,
                "name":       DEFAULT_LANGUAGE_NAME,
                "flag":       LANGUAGE_FLAGS[DEFAULT_LANGUAGE_CODE],
                "confidence": "low",
                "fallback":   True,
            }

        return {
            "code":       code,
            "name":       LANGUAGE_NAMES[code],
            "flag":       LANGUAGE_FLAGS[code],
            "confidence": "high",
            "fallback":   False,
        }
    except LangDetectException:
        return {
            "code":       DEFAULT_LANGUAGE_CODE,
            "name":       DEFAULT_LANGUAGE_NAME,
            "flag":       LANGUAGE_FLAGS[DEFAULT_LANGUAGE_CODE],
            "confidence": "low",
            "fallback":   True,
        }
