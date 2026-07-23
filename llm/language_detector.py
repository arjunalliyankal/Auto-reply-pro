from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Fix random seed so detection is deterministic
DetectorFactory.seed = 42

# ── Supported languages ──────────────────────────────────────────────────────
LANGUAGE_NAMES = {
    "en": "English",
    "ml": "Malayalam",
    "hi": "Hindi",
}

# Language code → flag emoji
LANGUAGE_FLAGS = {
    "en": "🇬🇧",
    "ml": "🇮🇳",
    "hi": "🇮🇳",
}

# ── Near-match aliases ───────────────────────────────────────────────────────
# langdetect sometimes confuses closely-related languages (e.g. Hindi ↔ Punjabi
# because they share the Devanagari / Gurmukhi scripts).  Map unsupported but
# related codes to the nearest supported language so the user gets the right
# response language instead of a fallback to English.
LANGUAGE_ALIASES = {
    # Devanagari-script languages → Hindi
    "pa": "hi",   # Punjabi
    "mr": "hi",   # Marathi
    "ne": "hi",   # Nepali
    "sa": "hi",   # Sanskrit
    "bh": "hi",   # Bihari
    # South-Indian languages → Malayalam (closest supported)
    "ta": "ml",   # Tamil
    "te": "ml",   # Telugu
    "kn": "ml",   # Kannada
}

SUPPORTED_CODES = set(LANGUAGE_NAMES.keys())

DEFAULT_LANGUAGE_CODE = "en"
DEFAULT_LANGUAGE_NAME = "English"
MIN_TEXT_LENGTH = 10   # Skip detection for very short inputs


def detect_language(text: str) -> dict:
    """
    Detect the language of an input string.
    Only English, Malayalam, and Hindi are supported; closely-related
    languages are aliased to the nearest supported code, and anything
    else falls back to English.

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

        # Remap near-match aliases to the closest supported language
        if code in LANGUAGE_ALIASES:
            code = LANGUAGE_ALIASES[code]

        # If still not in our supported set, fall back to English
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
