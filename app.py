import os
import time
import json
import streamlit as st

from ui.sidebar import render_sidebar
from ui.file_uploader import render_file_uploader
from ui.live_log import render_live_log
from ui.channel_config import render_channel_config
from rag.vector_store import load_index, retrieve
from llm.reply_generator import generate_reply
from channels.telegram_channel import TelegramChannel
from channels.gmail_channel import GmailChannel

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AutoReply Pro",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #0e1117; }
    [data-testid="stSidebar"] { background: #161b27; border-right: 1px solid #2d3748; }
    .main-title {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    .subtitle { color: #718096; font-size: 1rem; margin-top: 0; }
    .status-pill {
        display: inline-block;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .pill-running { background: #22543d; color: #68d391; }
    .pill-idle    { background: #2d3748; color: #a0aec0; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">🤖 AutoReply Pro</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-Powered Multi-Channel Business Reply Automation</p>', unsafe_allow_html=True)
st.divider()

# ── Sidebar ───────────────────────────────────────────────────────────────────
config = render_sidebar()

# ── Main Layout ───────────────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    # Knowledge base upload
    render_file_uploader()

    st.divider()

    # Channel setup guide
    render_channel_config()

with col_right:
    st.markdown("## 📨 Live Reply Log")
    log_container = st.empty()

    st.divider()

    # ── Automation controls ───────────────────────────────────────────────────
    st.markdown("## ▶️ Automation")

    index_exists = os.path.exists("data/faiss_index")
    if not index_exists:
        st.warning("⚠️ No knowledge base found. Upload documents and build the index first.")

    can_start = (
        index_exists
        and config["groq_key"]
        and (
            (config["use_telegram"] and config["telegram_key"])
            or (config["use_gmail"] and config["gmail_creds_path"])
        )
    )

    if not can_start and index_exists:
        missing = []
        if not config["groq_key"]:
            missing.append("Groq API Key")
        if not config["use_telegram"] and not config["use_gmail"]:
            missing.append("at least one active channel")
        elif config["use_telegram"] and not config["telegram_key"]:
            missing.append("Telegram Bot Token")
        st.info(f"ℹ️ Still needed: {', '.join(missing)}")

    start_btn = st.button(
        "▶️ Start Automation",
        disabled=not can_start,
        use_container_width=True,
        type="primary",
    )

    if start_btn:
        os.makedirs("logs", exist_ok=True)
        log_path = "logs/reply_log.jsonl"

        # Load FAISS index
        try:
            db = load_index()
        except Exception as e:
            st.error(f"❌ Failed to load knowledge base: {e}")
            st.stop()

        # Instantiate channels
        tg = TelegramChannel(config["telegram_key"]) if config["use_telegram"] and config["telegram_key"] else None
        gm = GmailChannel(config["gmail_creds_path"]) if config["use_gmail"] and config["gmail_creds_path"] else None

        log_entries: list[dict] = []
        stop_btn = st.button("⏹ Stop Automation", use_container_width=True)

        status_area = st.empty()
        status_area.markdown('<span class="status-pill pill-running">● Running</span>', unsafe_allow_html=True)

        while not stop_btn:
            # ── Telegram ──────────────────────────────────────────────────
            if tg:
                try:
                    for update in tg.get_updates():
                        parsed = tg.parse_message(update)
                        if parsed:
                            chat_id, msg_text = parsed
                            context = retrieve(msg_text, db)
                            reply = generate_reply("telegram", msg_text, context, config["groq_key"])
                            tg.send_reply(chat_id, reply)
                            entry = {"channel": "Telegram", "message": msg_text, "reply": reply, "ts": time.time()}
                            log_entries.append(entry)
                            with open(log_path, "a") as lf:
                                lf.write(json.dumps(entry) + "\n")
                except Exception as e:
                    st.warning(f"⚠️ Telegram error: {e}")

            # ── Gmail ─────────────────────────────────────────────────────
            if gm:
                try:
                    for email in gm.get_unread_messages():
                        body = gm.extract_body(email)
                        if not body.strip():
                            continue
                        thread_id = email["threadId"]
                        to_addr = gm.get_header(email, "From")
                        subject = gm.get_header(email, "Subject")
                        context = retrieve(body, db)
                        reply = generate_reply("email", body, context, config["groq_key"])
                        gm.send_reply(to_addr, subject, reply, thread_id)
                        gm.mark_as_read(email["id"])
                        entry = {"channel": "Email", "message": body[:500], "reply": reply, "ts": time.time()}
                        log_entries.append(entry)
                        with open(log_path, "a") as lf:
                            lf.write(json.dumps(entry) + "\n")
                except Exception as e:
                    st.warning(f"⚠️ Gmail error: {e}")

            # ── Render log ────────────────────────────────────────────────
            render_live_log(log_entries, log_container)
            time.sleep(5)

        status_area.markdown('<span class="status-pill pill-idle">● Stopped</span>', unsafe_allow_html=True)

    else:
        render_live_log([], log_container)
