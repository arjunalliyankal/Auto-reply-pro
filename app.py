import os
import time
import json
import streamlit as st

from config.settings import settings
from utils.mongo_logger import log_to_mongo

from ui.sidebar import render_sidebar
from ui.file_uploader import render_file_uploader
from ui.live_log import render_live_log
from ui.channel_config import render_channel_config
from rag.vector_store import load_index        # NEW
from llm.reply_generator import generate_reply
from channels.telegram_channel import TelegramChannel
from channels.gmail_channel import GmailChannel
from memory.identity_store import resolve_canonical_id
from memory.onboarding import handle_onboarding

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

# ── Top section: controls centered ──────────────────────────────────────
_, ctrl_col, _ = st.columns([1, 4, 1])

with ctrl_col:
    # Knowledge base upload
    render_file_uploader()

    st.divider()

    # Channel setup guide
    render_channel_config()

    st.divider()

    # ── Automation controls ───────────────────────────────────────────────
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

        mongo_uri = config["mongo_uri"]
        db_name   = config["db_name"]

        # Load FAISS text index
        try:
            db = load_index()
        except Exception as e:
            st.error(f"❌ Failed to load knowledge base: {e}")
            st.stop()

        # Image metadata will be hot-reloaded inside the polling loop

        # Instantiate channels
        tg = TelegramChannel(config["telegram_key"]) if config["use_telegram"] and config["telegram_key"] else None
        gm = GmailChannel(config["gmail_creds_path"]) if config["use_gmail"] and config["gmail_creds_path"] else None

        log_entries: list[dict] = []
        stop_btn = st.button("⏹ Stop Automation", use_container_width=True)

        status_area = st.empty()
        status_area.markdown('<span class="status-pill pill-running">● Running</span>', unsafe_allow_html=True)

# ── Bottom section: live log full-width centered ──────────────────────────
st.divider()
st.markdown(
    "<h3 style='text-align:center; margin-bottom:.25rem;'>💬 Live Reply Log</h3>",
    unsafe_allow_html=True,
)
_, log_col, _ = st.columns([1, 6, 1])
with log_col:
    log_container = st.empty()

# ── Automation polling loop ───────────────────────────────────────────────
if start_btn:
    while not stop_btn:
        # Hot-reload image metadata so manual uploads are instantly available
        import json
        if os.path.exists("data/image_metadata.json"):
            with open("data/image_metadata.json", "r", encoding="utf-8") as f:
                image_metadata = json.load(f)
        else:
            image_metadata = []

        # ── Telegram ──────────────────────────────────────────────────
        if tg:
            try:
                for update in tg.get_updates():
                    parsed = tg.parse_message(update)
                    if not parsed:
                        continue

                    chat_id, msg_text = parsed
                    tid = str(chat_id)

                    # Resolve canonical_id (email) for this Telegram user
                    canonical_id = resolve_canonical_id(
                        "telegram", tid, mongo_uri, db_name
                    )

                    if canonical_id is None:
                        # New / pending user — run onboarding flow
                        ob = handle_onboarding(tid, msg_text, mongo_uri, db_name)
                        tg.send_reply(chat_id, ob["reply"])

                        if ob["status"] in ("ask_email", "waiting"):
                            # Not ready to process as a business query yet
                            continue
                        elif ob["status"] == "skipped":
                            # Max attempts — fall back to telegram_id
                            canonical_id = tid
                        elif ob["status"] in ("success", "already_linked"):
                            canonical_id = ob["canonical_id"]
                            # The message was the email — wait for next real message
                            continue

                    result = generate_reply(
                        channel="telegram",
                        message=msg_text,
                        db=db,
                        groq_api_key=config["groq_key"],
                        user_id=canonical_id,
                        mongo_uri=mongo_uri,
                        db_name=db_name,
                        available_images=image_metadata,            # ← NEW (LLM selection)
                        override_lang=config.get("override_lang", "Auto-detect"),
                    )
                    # Use image-aware send if images matched  ← NEW
                    if result.get("images"):
                        tg.send_reply_with_images(chat_id, result["reply"], result["images"])
                    else:
                        tg.send_reply(chat_id, result["reply"])
                    entry = {
                        "channel":      "Telegram",
                        "canonical_id": canonical_id,
                        "message":      msg_text,
                        "reply":        result["reply"],
                        "lang_code":    result["language"]["code"],
                        "lang_name":    result["language"]["name"],
                        "lang_flag":    result["language"]["flag"],
                        "fallback":     result["language"]["fallback"],
                        "turns":        result.get("turns_in_context", 0),
                        "ts":           time.time(),
                    }
                    log_entries.append(entry)
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(json.dumps(entry) + "\n")
            except Exception as e:
                with ctrl_col:
                    st.warning(f"⚠️ Telegram error: {e}")

        # ── Gmail ─────────────────────────────────────────────────────
        if gm:
            try:
                for email in gm.get_unread_messages():
                    body = gm.extract_body(email)
                    if not body.strip():
                        continue
                    thread_id = email["threadId"]
                    to_addr   = gm.get_header(email, "From")
                    subject   = gm.get_header(email, "Subject")

                    import email.utils as email_utils
                    _, clean_email = email_utils.parseaddr(to_addr)
                    clean_email = clean_email.lower()

                    # Email address IS the canonical_id;
                    # auto-creates identity record on first contact
                    canonical_id = resolve_canonical_id(
                        "email", clean_email, mongo_uri, db_name
                    )

                    result = generate_reply(
                        channel="email",
                        message=body,
                        db=db,
                        groq_api_key=config["groq_key"],
                        user_id=canonical_id,
                        mongo_uri=mongo_uri,
                        db_name=db_name,
                        available_images=image_metadata,                # ← NEW (LLM selection)
                        override_lang=config.get("override_lang", "Auto-detect"),
                    )
                    # Use image-aware send if images matched  ← NEW
                    if result.get("images"):
                        gm.send_reply_with_images(
                            to_addr, subject, result["reply"],
                            thread_id, result["images"]
                        )
                    else:
                        gm.send_reply(to_addr, subject, result["reply"], thread_id)
                    gm.mark_as_read(email["id"])
                    entry = {
                        "channel":      "Email",
                        "canonical_id": canonical_id,
                        "message":      body[:500],
                        "reply":        result["reply"],
                        "lang_code":    result["language"]["code"],
                        "lang_name":    result["language"]["name"],
                        "lang_flag":    result["language"]["flag"],
                        "fallback":     result["language"]["fallback"],
                        "turns":        result.get("turns_in_context", 0),
                        "ts":           time.time(),
                    }
                    log_entries.append(entry)
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(json.dumps(entry) + "\n")
            except Exception as e:
                with ctrl_col:
                    st.warning(f"⚠️ Gmail error: {e}")

        # ── Render live log into bottom container ──────────────────────
        render_live_log(log_entries, log_container)
        time.sleep(5)

    status_area.markdown('<span class="status-pill pill-idle">● Stopped</span>', unsafe_allow_html=True)

else:
    render_live_log([], log_container)

# ── Attachments Library ───────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<h3 style='text-align:center; margin-bottom:.25rem;'>🖼️ Attachments Library</h3>",
    unsafe_allow_html=True,
)
_, img_col, _ = st.columns([1, 6, 1])

import json
if os.path.exists("data/image_metadata.json"):
    with open("data/image_metadata.json", "r", encoding="utf-8") as f:
        loaded_image_meta = json.load(f)
else:
    loaded_image_meta = []


with img_col:
    if not loaded_image_meta:
        st.info(
            "No attachments extracted yet. Upload a PDF to automatically extract embedded images, "
            "or use the manual upload form below."
        )
    else:
        st.write(f"**{len(loaded_image_meta)} attachment(s) available for LLM matching**")
        cols = st.columns(2)  # Use 2 columns so we have enough room for the description
        for i, meta in enumerate(loaded_image_meta):
            with cols[i % 2]:
                fname = os.path.basename(meta["file_path"])
                if fname.lower().endswith(".pdf"):
                    # We can't render a PDF perfectly in st.image. Show an icon instead.
                    st.markdown(f"📄 **{fname}** (PDF Document)")
                else:
                    st.image(
                        meta["file_path"],
                        caption=fname,
                        use_container_width=True,
                    )
                with st.expander("Show LLM Reference Description"):
                    st.caption(f"**Source:** {meta['source_file']} (Page {meta['page_number']})")
                    st.write(meta["context_text"])
                    
    # MANUAL UPLOAD
    st.divider()
    st.subheader("➕ Add Manual Attachment")
    with st.expander("Upload independent image or PDF"):
        with st.form("manual_attachment_form", clear_on_submit=True):
            manual_file = st.file_uploader("Select file", type=["png", "jpg", "jpeg", "pdf"])
            manual_desc = st.text_area(
                "Description", 
                help="Tell the LLM what this file is about and when it should use it. E.g. 'Use this to show the pricing tiers.'"
            )
            submitted = st.form_submit_button("Add to Library")

            if submitted and manual_file and manual_desc.strip():
                os.makedirs("data/images", exist_ok=True)
                file_path = f"data/images/{manual_file.name}"
                with open(file_path, "wb") as f:
                    f.write(manual_file.getbuffer())

                new_meta = {
                    "file_path": file_path,
                    "source_file": "Manual Upload",
                    "page_number": "-",
                    "context_text": manual_desc.strip()
                }
                loaded_image_meta.append(new_meta)
                with open("data/image_metadata.json", "w", encoding="utf-8") as out_f:
                    json.dump(loaded_image_meta, out_f, indent=2)
                st.success(f"Added {manual_file.name} to the library!")
                st.rerun()

