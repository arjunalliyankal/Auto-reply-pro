import streamlit as st


def render_sidebar() -> dict:
    """
    Renders the sidebar configuration panel and returns collected values.

    Returns:
        dict with keys: gemini_key, telegram_key, gmail_creds_path,
                        use_telegram, use_gmail
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
        gmail_creds_file = st.file_uploader(
            "Upload credentials.json",
            type=["json"],
            key="gmail_creds_uploader",
        )
        gmail_creds_path = None
        if gmail_creds_file is not None:
            import os
            os.makedirs("data", exist_ok=True)
            path = "data/gmail_creds.json"
            with open(path, "wb") as f:
                f.write(gmail_creds_file.read())
            gmail_creds_path = path
            st.success("✅ credentials.json saved")

        st.divider()

        # ── Channel Toggles ───────────────────────────────────────────────
        st.markdown("### 📡 Active Channels")
        use_telegram = st.toggle("🤖 Telegram", value=False, key="use_telegram")
        use_gmail = st.toggle("📬 Gmail", value=False, key="use_gmail")

        st.divider()

        # ── Coming Soon ───────────────────────────────────────────────────
        st.markdown("### 💡 Coming Soon (Free)")
        st.info(
            "**WhatsApp** — via Twilio Sandbox\n\n"
            "**Discord** — via Discord Bot API\n\n"
            "**Slack** — via Slack App\n\n"
            "**Facebook Messenger** — via Meta API\n\n"
            "**Instagram DMs** — via Meta API"
        )

    return {
        "groq_key": groq_key,
        "telegram_key": telegram_key,
        "gmail_creds_path": gmail_creds_path,
        "use_telegram": use_telegram,
        "use_gmail": use_gmail,
    }
