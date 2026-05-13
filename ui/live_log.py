import streamlit as st


def render_live_log(log_entries: list[dict], container) -> None:
    """
    Renders the live reply log in a Streamlit container.

    Args:
        log_entries: List of dicts with keys 'channel', 'message', 'reply'.
        container: A Streamlit empty() container to re-render into.
    """
    with container.container():
        if not log_entries:
            st.info("📭 No replies sent yet. Start automation to see live logs here.")
            return

        st.markdown(f"**{len(log_entries)} message(s) processed**")
        for entry in reversed(log_entries[-20:]):
            channel_icon = "🤖" if entry["channel"] == "Telegram" else "📬"
            label = f"{channel_icon} [{entry['channel']}]  {entry['message'][:80]}{'…' if len(entry['message']) > 80 else ''}"
            with st.expander(label):
                st.markdown("**📥 Incoming Message:**")
                st.code(entry["message"], language=None)
                st.markdown("**📤 Reply Sent:**")
                st.markdown(entry["reply"])
