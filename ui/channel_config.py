import streamlit as st


def render_channel_config() -> None:
    """
    Renders per-channel configuration help and status information.
    This is displayed in the main panel to guide users with channel setup.
    """
    st.markdown("## 📡 Channel Setup Guide")

    tab_tg, tab_gmail = st.tabs(["🤖 Telegram", "📬 Gmail"])

    with tab_tg:
        st.markdown("""
**How to set up Telegram (Free ✅)**

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot` and follow the prompts to create your bot
3. Copy the **Bot Token** (format: `123456789:ABCdefGHIjklMNO...`)
4. Paste it into the **Telegram Bot Token** field in the sidebar
5. Toggle **Telegram** ON in Active Channels
6. Click **▶️ Start Automation**

Your bot will now auto-reply to every message it receives!
        """)

    with tab_gmail:
        st.markdown("""
**How to set up Gmail (Free ✅)**

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable the **Gmail API**
3. Go to **APIs & Services → Credentials**
4. Create **OAuth 2.0 Client ID** (Desktop app)
5. Download `credentials.json`
6. Upload `credentials.json` via the sidebar uploader
7. Toggle **Gmail** ON in Active Channels
8. Click **▶️ Start Automation**

The system scans your inbox for unread emails and replies within the thread.
        """)
