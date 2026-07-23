import time
import streamlit as st


# ── Colour palette for different users ───────────────────────────────────────
_USER_COLOURS = [
    "#7C3AED", "#8B5CF6", "#A78BFA", "#EC4899",
    "#F472B6", "#D946EF", "#C084FC", "#6366F1",
]


def _user_colour(canonical_id: str) -> str:
    """Deterministically pick a colour for a canonical_id."""
    return _USER_COLOURS[hash(canonical_id) % len(_USER_COLOURS)]


def _channel_icon(channel: str) -> str:
    return "✈️" if channel == "Telegram" else "📬"


def _fmt_time(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


# ── Public renderer ───────────────────────────────────────────────────────────

def render_live_log(log_entries: list[dict], container) -> None:
    """
    Renders the live reply log, centred at the bottom of Tab 1.

    Groups exchanges by canonical_id so each user's conversation
    appears together as a coloured chat thread.

    Each entry dict should contain:
        channel, message, reply, canonical_id (optional),
        lang_name, lang_flag, fallback (optional), ts (epoch float)
    """
    with container.container():
        if not log_entries:
            st.markdown(
                """
                <div style="
                    text-align:center;
                    color:#8B5CF6;
                    padding:2.5rem 0;
                    font-size:1rem;
                ">
                    📭 No replies sent yet — start automation to see live conversations here.
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        # ── Group by canonical_id, preserve insertion order ───────────────────
        groups: dict[str, list[dict]] = {}
        for entry in log_entries:
            uid = entry.get("canonical_id") or entry.get("user_id") or "unknown"
            groups.setdefault(uid, []).append(entry)

        total_msgs = len(log_entries)
        total_users = len(groups)
        st.markdown(
            f"<div style='text-align:center; color:#8B5CF6; margin-bottom:.5rem;'>"
            f"💬 <b>{total_msgs}</b> message(s) across <b>{total_users}</b> user(s)"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── Render each user block ────────────────────────────────────────────
        for uid, entries in groups.items():
            colour = _user_colour(uid)
            latest = entries[-1]
            ch_icon = _channel_icon(latest["channel"])
            lang_label = ""
            if "lang_name" in latest:
                flag = latest.get("lang_flag", "🌐")
                lang = latest.get("lang_name", "")
                lang_label = f" · {flag} {lang}"
                if latest.get("fallback"):
                    lang_label += " (fallback)"

            header = (
                f"{ch_icon} **{uid}**"
                f"{lang_label}"
                f" · {len(entries)} msg(s)"
                f" · last {_fmt_time(latest['ts'])}"
            )

            with st.expander(header, expanded=(total_users == 1)):
                # Inject chat bubble CSS scoped to this expander
                st.markdown(
                    f"""
                    <style>
                    .chat-wrap-{uid[:8].replace("@","at").replace(".","_")} {{
                        display: flex;
                        flex-direction: column;
                        gap: 0.6rem;
                        padding: 0.5rem 0;
                    }}
                    .bubble-user {{
                        align-self: flex-end;
                        background: {colour}22;
                        border: 1px solid {colour}55;
                        border-radius: 16px 16px 4px 16px;
                        padding: 0.55rem 1rem;
                        max-width: 75%;
                        color: #1E1B4B;
                        font-size: 0.92rem;
                    }}
                    .bubble-bot {{
                        align-self: flex-start;
                        background: #FFFFFF;
                        border: 1px solid #8B5CF6;
                        border-radius: 16px 16px 16px 4px;
                        padding: 0.55rem 1rem;
                        max-width: 75%;
                        color: #1E1B4B;
                        font-size: 0.92rem;
                    }}
                    .bubble-meta {{
                        font-size: 0.72rem;
                        color: #8B5CF6;
                        opacity: 0.8;
                        margin-top: 2px;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                safe_uid = uid[:8].replace("@", "at").replace(".", "_")
                html_parts = [f'<div class="chat-wrap-{safe_uid}">']

                for e in entries:
                    ts_str = _fmt_time(e["ts"])
                    ch = e.get("channel", "")
                    msg = e["message"].replace("<", "&lt;").replace(">", "&gt;")
                    reply = e["reply"].replace("<", "&lt;").replace(">", "&gt;")

                    # User bubble (right-aligned)
                    html_parts.append(
                        f'<div class="bubble-user">'
                        f'{msg}'
                        f'<div class="bubble-meta">{_channel_icon(ch)} {ch} · {ts_str}</div>'
                        f'</div>'
                    )
                    # Bot bubble (left-aligned)
                    html_parts.append(
                        f'<div class="bubble-bot">'
                        f'🤖 {reply}'
                        f'<div class="bubble-meta">AutoReply Pro · {ts_str}</div>'
                        f'</div>'
                    )

                html_parts.append("</div>")
                st.markdown("\n".join(html_parts), unsafe_allow_html=True)
