from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Fix random seed so detection is deterministic
DetectorFactory.seed = 42

# ISO 639-1 → human-readable language name
LANGUAGE_NAMES = {
    "af": "Afrikaans",    "sq": "Albanian",      "am": "Amharic",
    "ar": "Arabic",       "hy": "Armenian",      "az": "Azerbaijani",
    "eu": "Basque",       "be": "Belarusian",    "bn": "Bengali",
    "bs": "Bosnian",      "bg": "Bulgarian",     "ca": "Catalan",
    "zh-cn": "Chinese (Simplified)",             "zh-tw": "Chinese (Traditional)",
    "hr": "Croatian",     "cs": "Czech",         "da": "Danish",
    "nl": "Dutch",        "en": "English",       "et": "Estonian",
    "fi": "Finnish",      "fr": "French",        "gl": "Galician",
    "ka": "Georgian",     "de": "German",        "el": "Greek",
    "gu": "Gujarati",     "ht": "Haitian Creole","ha": "Hausa",
    "he": "Hebrew",       "hi": "Hindi",         "hu": "Hungarian",
    "is": "Icelandic",    "id": "Indonesian",    "ga": "Irish",
    "it": "Italian",      "ja": "Japanese",      "kn": "Kannada",
    "kk": "Kazakh",       "km": "Khmer",         "ko": "Korean",
    "ku": "Kurdish",      "ky": "Kyrgyz",        "lo": "Lao",
    "lv": "Latvian",      "lt": "Lithuanian",    "lb": "Luxembourgish",
    "mk": "Macedonian",   "mg": "Malagasy",      "ms": "Malay",
    "ml": "Malayalam",    "mt": "Maltese",       "mi": "Maori",
    "mr": "Marathi",      "mn": "Mongolian",     "my": "Burmese",
    "ne": "Nepali",       "no": "Norwegian",     "or": "Odia",
    "ps": "Pashto",       "fa": "Persian",       "pl": "Polish",
    "pt": "Portuguese",   "pa": "Punjabi",       "ro": "Romanian",
    "ru": "Russian",      "sr": "Serbian",       "si": "Sinhala",
    "sk": "Slovak",       "sl": "Slovenian",     "so": "Somali",
    "es": "Spanish",      "sw": "Swahili",       "sv": "Swedish",
    "tl": "Filipino",     "tg": "Tajik",         "ta": "Tamil",
    "tt": "Tatar",        "te": "Telugu",        "th": "Thai",
    "tr": "Turkish",      "tk": "Turkmen",       "uk": "Ukrainian",
    "ur": "Urdu",         "ug": "Uyghur",        "uz": "Uzbek",
    "vi": "Vietnamese",   "cy": "Welsh",         "xh": "Xhosa",
    "yi": "Yiddish",      "yo": "Yoruba",        "zu": "Zulu",
}

# Language code → flag emoji (common ones)
LANGUAGE_FLAGS = {
    "ar": "🇸🇦", "bn": "🇧🇩", "zh-cn": "🇨🇳", "zh-tw": "🇹🇼",
    "nl": "🇳🇱", "en": "🇬🇧", "fr": "🇫🇷", "de": "🇩🇪",
    "el": "🇬🇷", "gu": "🇮🇳", "hi": "🇮🇳", "id": "🇮🇩",
    "it": "🇮🇹", "ja": "🇯🇵", "kn": "🇮🇳", "ko": "🇰🇷",
    "ml": "🇮🇳", "mr": "🇮🇳", "ms": "🇲🇾", "fa": "🇮🇷",
    "pl": "🇵🇱", "pt": "🇧🇷", "pa": "🇮🇳", "ro": "🇷🇴",
    "ru": "🇷🇺", "es": "🇪🇸", "sw": "🇰🇪", "sv": "🇸🇪",
    "ta": "🇮🇳", "te": "🇮🇳", "th": "🇹🇭", "tr": "🇹🇷",
    "uk": "🇺🇦", "ur": "🇵🇰", "vi": "🇻🇳",
}

DEFAULT_LANGUAGE_CODE = "en"
DEFAULT_LANGUAGE_NAME = "English"
MIN_TEXT_LENGTH = 10   # Skip detection for very short inputs

def detect_language(text: str) -> dict:
    """
    Detect the language of an input string.

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
            "code": DEFAULT_LANGUAGE_CODE,
            "name": DEFAULT_LANGUAGE_NAME,
            "flag": LANGUAGE_FLAGS.get(DEFAULT_LANGUAGE_CODE, "🌐"),
            "confidence": "low",
            "fallback": True,
        }

    try:
        code = detect(text.strip())
        name = LANGUAGE_NAMES.get(code, code.upper())
        flag = LANGUAGE_FLAGS.get(code, "🌐")
        return {
            "code": code,
            "name": name,
            "flag": flag,
            "confidence": "high",
            "fallback": False,
        }
    except LangDetectException:
        return {
            "code": DEFAULT_LANGUAGE_CODE,
            "name": DEFAULT_LANGUAGE_NAME,
            "flag": "🌐",
            "confidence": "low",
            "fallback": True,
        }
