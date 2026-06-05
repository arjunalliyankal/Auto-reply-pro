import streamlit as st


def render_live_log(log_entries: list[dict], container) -> None:
    """
    Renders the live reply log in a Streamlit container.

    Args:
        log_entries: List of dicts with keys 'channel', 'message', 'reply',
                     and optional 'lang_code', 'lang_name', 'lang_flag', 'fallback'.
        container: A Streamlit empty() container to re-render into.
    """
    with container.container():
        if not log_entries:
            st.info("📭 No replies sent yet. Start automation to see live logs here.")
            return

        st.markdown(f"**{len(log_entries)} message(s) processed**")
        for entry in reversed(log_entries[-20:]):
            channel_icon = "🤖" if entry["channel"] == "Telegram" else "📬"
            
            if "lang_name" in entry:
                lang_label = (
                    f"{entry['lang_flag']} {entry['lang_name']}"
                    if not entry.get("fallback")
                    else f"🌐 {entry['lang_name']} (fallback)"
                )
                label = f"[{entry['channel']}] {lang_label} — {entry['message'][:70]}..."
                with st.expander(label):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**📥 Incoming Message:**")
                        st.code(entry["message"], language=None)
                    with col2:
                        st.markdown(f"**📤 Reply Sent:** *(in {entry['lang_name']})*")
                        st.markdown(entry["reply"])
            else:
                label = f"{channel_icon} [{entry['channel']}]  {entry['message'][:80]}{'…' if len(entry['message']) > 80 else ''}"
                with st.expander(label):
                    st.markdown("**📥 Incoming Message:**")
                    st.code(entry["message"], language=None)
                    st.markdown("**📤 Reply Sent:**")
                    st.markdown(entry["reply"])
