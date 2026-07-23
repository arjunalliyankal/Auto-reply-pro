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
    [data-testid="stAppViewContainer"] { background: #F5F3FF; }
    [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #8B5CF6; }
    .main-title {
        background: linear-gradient(135deg, #7C3AED 0%, #EC4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    .subtitle { color: #4C1D95; font-size: 1rem; margin-top: 0; }
    .status-pill {
        display: inline-block;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .pill-running { background: #7C3AED; color: #FFFFFF; }
    .pill-idle    { background: #E2E8F0; color: #475569; }
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
    st.markdown("##  Automation")

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
        width="stretch",
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
        stop_btn = st.button("⏹ Stop Automation", width="stretch")

        status_area = st.empty()
        status_area.markdown('<span class="status-pill pill-running">● Running</span>', unsafe_allow_html=True)

# ── Bottom section: live log full-width centered ──────────────────────────
st.divider()
st.markdown(
    "<h3 style='text-align:center; margin-bottom:.25rem;'> Live Reply Log</h3>",
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

                    chat_id, msg_input = parsed
                    tid = str(chat_id)

                    # Handle audio inputs
                    from utils.audio_processor import is_audio, transcribe_audio
                    if is_audio(msg_input):
                        st.info("🎙️ Transcribing voice message...")
                        msg_text = transcribe_audio(
                            msg_input,
                            api_key=config["groq_key"],
                            bot_token=config["telegram_key"]
                        )
                        if not msg_text:
                            tg.send_reply(chat_id, "Sorry, I could not transcribe your voice message.")
                            continue
                    else:
                        msg_text = msg_input

                    # Resolve canonical_id (email) for this Telegram user
                    canonical_id = resolve_canonical_id(
                        "telegram", tid, mongo_uri, db_name
                    )

                    if canonical_id is None:
                        # New / pending user — run onboarding flow
                        ob = handle_onboarding(tid, msg_text, mongo_uri, db_name)
                        
                        if ob["status"] == "success":
                            first_msg_imgs = [img for img in image_metadata if img.get("send_on_first_message")]
                            if first_msg_imgs:
                                tg.send_reply_with_images(chat_id, ob["reply"], first_msg_imgs)
                            else:
                                tg.send_reply(chat_id, ob["reply"])
                            
                            # Save onboarding as a system turn so history len > 0, preventing duplicate triggers
                            from memory.memory_store import save_turn
                            save_turn(
                                user_id=ob["canonical_id"],
                                channel="telegram",
                                user_msg=msg_text,
                                bot_reply=ob["reply"],
                                lang_info={"code": "en", "name": "English", "flag": "🇬🇧", "fallback": False},
                                model="system",
                                mongo_uri=mongo_uri,
                                db_name=db_name
                            )
                        else:
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
            import email.utils as email_utils
            import traceback
            try:
                unread = gm.get_unread_messages()
                print(f"[Gmail] Found {len(unread)} unread message(s)")
            except Exception as e:
                with ctrl_col:
                    st.warning(f"⚠️ Gmail fetch error: {e}")
                unread = []

            for msg in unread:
                try:
                    body = gm.extract_body(msg)
                    print(f"[Gmail] msg id={msg.get('id')} body_len={len(body)}")
                    if not body.strip():
                        print(f"[Gmail] Skipping msg {msg.get('id')} — empty body")
                        gm.mark_as_read(msg["id"])   # mark so we don't re-process
                        continue

                    thread_id   = msg["threadId"]
                    to_addr     = gm.get_header(msg, "From")
                    subject     = gm.get_header(msg, "Subject")

                    _, clean_email = email_utils.parseaddr(to_addr)
                    clean_email = clean_email.lower()

                    print(f"[Gmail] Processing from={clean_email} subject={subject!r}")

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
                        available_images=image_metadata,
                        override_lang=config.get("override_lang", "Auto-detect"),
                    )

                    # Use image-aware send if images matched
                    if result.get("images"):
                        gm.send_reply_with_images(
                            to_addr, subject, result["reply"],
                            thread_id, result["images"]
                        )
                    else:
                        gm.send_reply(to_addr, subject, result["reply"], thread_id)

                    gm.mark_as_read(msg["id"])
                    print(f"[Gmail] Replied and marked read: {msg.get('id')}")

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
                    tb = traceback.format_exc()
                    print(f"[Gmail] Error on msg {msg.get('id')}: {tb}")
                    with ctrl_col:
                        st.warning(f"⚠️ Gmail error (msg {msg.get('id')}): {e}")



        # ── Render live log into bottom container ──────────────────────
        render_live_log(log_entries, log_container)
        time.sleep(5)

    status_area.markdown('<span class="status-pill pill-idle">● Stopped</span>', unsafe_allow_html=True)

else:
    render_live_log([], log_container)

# ── Attachments Library ───────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<h3 style='text-align:center; margin-bottom:.25rem;'> Attachments Library</h3>",
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
        cols = st.columns(3)  # Use 3 columns to organize the attachment library
        for i, meta in enumerate(loaded_image_meta):
            with cols[i % 3]:
                fname = os.path.basename(meta["file_path"])
                
                is_pdf = fname.lower().endswith(".pdf")
                is_audio = fname.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac', '.opus'))
                
                if is_pdf:
                    st.markdown(f"📄 **{fname}** (PDF Document)")
                elif is_audio:
                    st.markdown(f"🎵 **{fname}** (Audio File)")
                    st.audio(meta["file_path"])
                else:
                    st.image(
                        meta["file_path"],
                        caption=fname,
                        width=150,  # Decreased size in UI
                    )
                
                if meta.get("send_on_first_message"):
                    st.markdown("⚡ *Send on first message*")
                
                expander_title = "Show Description" if not meta.get("send_on_first_message") else "Show Context/Description"
                with st.expander(expander_title):
                    src_file = meta.get("source_file", "Manual Upload")
                    pg_num = meta.get("page_number", "-")
                    st.caption(f"**Source:** {src_file} (Page {pg_num})")
                    desc_text = meta.get("context_text", "").strip()
                    st.write(desc_text if desc_text else "*(No description)*")
                    if st.button("🗑️ Delete", key=f"del_attach_{i}"):
                        try:
                            if os.path.exists(meta["file_path"]):
                                os.remove(meta["file_path"])
                        except Exception:
                            pass
                        loaded_image_meta.pop(i)
                        with open("data/image_metadata.json", "w", encoding="utf-8") as out_f:
                            json.dump(loaded_image_meta, out_f, indent=2)
                        st.rerun()
    # MANUAL UPLOAD
    st.divider()
    st.subheader("➕ Add Manual Attachment")
    with st.expander("Upload independent image, PDF, or audio file"):
        with st.form("manual_attachment_form", clear_on_submit=True):
            manual_file = st.file_uploader(
                "Select file", 
                type=["png", "jpg", "jpeg", "pdf", "mp3", "wav", "ogg", "m4a", "flac", "opus"]
            )
            send_on_first_msg = st.checkbox(
                "Send on first message", 
                help="Automatically attach and send this file on the first message of a user conversation."
            )
            manual_desc = st.text_area(
                "Description", 
                help="Tell the LLM what this file is about. (Optional if 'Send on first message' is checked)"
            )
            submitted = st.form_submit_button("Add to Library")

            if submitted and manual_file:
                # Validation: Description is optional ONLY if send_on_first_msg is checked
                if not send_on_first_msg and not manual_desc.strip():
                    st.error("❌ Description is required unless 'Send on first message' is checked.")
                else:
                    os.makedirs("data/images", exist_ok=True)
                    file_path = f"data/images/{manual_file.name}"
                    with open(file_path, "wb") as f:
                        f.write(manual_file.getbuffer())

                    new_meta = {
                        "file_path": file_path,
                        "source_file": "Manual Upload",
                        "page_number": "-",
                        "context_text": manual_desc.strip(),
                        "send_on_first_message": send_on_first_msg
                    }
                    loaded_image_meta.append(new_meta)
                    with open("data/image_metadata.json", "w", encoding="utf-8") as out_f:
                        json.dump(loaded_image_meta, out_f, indent=2)
                    st.success(f"Added {manual_file.name} to the library!")
                    st.rerun()

