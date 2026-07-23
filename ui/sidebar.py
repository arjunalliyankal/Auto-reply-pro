import streamlit as st
from llm.language_detector import LANGUAGE_NAMES
from config.settings import settings


def render_sidebar() -> dict:
    """
    Renders the sidebar configuration panel and returns collected values.

    Returns:
        dict with keys: groq_key, telegram_key, gmail_creds_path,
                        use_telegram, use_gmail, override_lang,
                        mongo_uri, db_name
    """
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")

        # ── API Keys ──────────────────────────────────────────────────────
        st.markdown("### 🔑 API Keys")
        groq_key = st.text_input(
            "Groq API Key",
            type="password",
            key="groq_key",
            placeholder="gsk_...",
        )
        telegram_key = st.text_input(
            "Telegram Bot Token",
            type="password",
            key="telegram_key",
            placeholder="123456:ABC-...",
        )

        # ── Gmail Credentials ─────────────────────────────────────────────
        st.markdown("### 📧 Gmail OAuth2")
        import os as _os
        _CREDS_PATH = "data/gmail_creds.json"
        _TOKEN_PATH = "data/token.json"

        # Auto-detect existing credentials so user doesn't re-upload every session
        gmail_creds_path = _CREDS_PATH if _os.path.exists(_CREDS_PATH) else None

        if gmail_creds_path and _os.path.exists(_TOKEN_PATH):
            st.success("✅ Gmail already authorised (token on disk)")
        elif gmail_creds_path:
            st.info("ℹ️ credentials.json found — OAuth will run on first start")

        gmail_creds_file = st.file_uploader(
            "Re-upload credentials.json (only needed to change account)",
            type=["json"],
            key="gmail_creds_uploader",
        )
        if gmail_creds_file is not None:
            _os.makedirs("data", exist_ok=True)
            with open(_CREDS_PATH, "wb") as f:
                f.write(gmail_creds_file.read())
            gmail_creds_path = _CREDS_PATH
            st.success("✅ credentials.json saved")

        st.divider()

        # ── MongoDB Config ────────────────────────────────────────────────
        st.markdown("### 🗄️ MongoDB")
        mongo_uri = st.text_input(
            "MongoDB URI",
            value=settings.mongo_uri,
            key="mongo_uri",
            help="Local: mongodb://localhost:27017 · Atlas: mongodb+srv://...",
        )
        db_name = st.text_input(
            "Database Name",
            value=settings.mongo_db_name,
            key="db_name",
        )

        if st.button("🔌 Test Connection", key="test_mongo"):
            try:
                from pymongo import MongoClient
                c = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
                c.admin.command("ping")
                st.success("✅ MongoDB connected")
            except Exception as e:
                st.error(f"❌ {e}")

        st.divider()

        # ── Channel Toggles ───────────────────────────────────────────────
        st.markdown("### 📡 Active Channels")
        use_telegram = st.toggle("🤖 Telegram", value=False, key="use_telegram")
        use_gmail = st.toggle("📬 Gmail", value=False, key="use_gmail")

        # ── Multilingual ──────────────────────────────────────────────────
        st.markdown("### 🌐 Multilingual")
        override_lang = st.selectbox(
            "🔒 Force Reply Language (optional)",
            options=["Auto-detect"] + sorted(LANGUAGE_NAMES.values()),
            index=0,
            key="override_lang",
        )

        st.divider()


        # ── Coming Soon (other channels) ──────────────────────────────────
        st.markdown("### 💡 Coming Soon (Free)")
        st.info(
            "**Discord** — via Discord Bot API\n\n"
            "**Slack** — via Slack App\n\n"
            "**Facebook Messenger** — via Meta API\n\n"
            "**Instagram DMs** — via Meta API"
        )

    return {
        "groq_key":        groq_key,
        "telegram_key":    telegram_key,
        "gmail_creds_path": gmail_creds_path,
        "use_telegram":    use_telegram,
        "use_gmail":       use_gmail,
        "override_lang":   override_lang,
        "mongo_uri":       mongo_uri,
        "db_name":         db_name,
    }
