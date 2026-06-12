import requests
from channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    """Telegram Bot channel — uses long-polling via getUpdates."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.offset = 0

    def get_updates(self) -> list[dict]:
        """Poll Telegram for new updates."""
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.offset, "timeout": 0},
                timeout=10,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])
            if updates:
                self.offset = updates[-1]["update_id"] + 1
            return updates
        except Exception as e:
            print(f"[Telegram] Error fetching updates: {e}")
            return []

    def get_messages(self) -> list[dict]:
        """Implements BaseChannel interface — wraps get_updates."""
        return self.get_updates()

    def send_reply(self, chat_id: int, text: str) -> None:  # type: ignore[override]
        """Send a text reply to a Telegram chat with preserved indentation."""
        formatted_text = self.format_indentation(text)
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": formatted_text},
                timeout=10,
            )
        except Exception as e:
            print(f"[Telegram] Error sending reply: {e}")

    def format_indentation(self, text: str) -> str:
        """
        Preserves indentations (leading spaces/tabs) in Telegram messages by replacing 
        leading whitespace on each line with non-breaking spaces (\u00A0).
        """
        if not text:
            return text
        lines = text.split("\n")
        formatted_lines = []
        for line in lines:
            leading_ws = ""
            rest_of_line = line
            while rest_of_line and rest_of_line[0] in (" ", "\t"):
                if rest_of_line[0] == " ":
                    leading_ws += "\u00A0"
                else:
                    leading_ws += "\u00A0\u00A0\u00A0\u00A0"
                rest_of_line = rest_of_line[1:]
            formatted_lines.append(leading_ws + rest_of_line)
        return "\n".join(formatted_lines)

    def parse_message(self, update: dict) -> tuple[int, str] | None:
        """Extract (chat_id, text) from a raw update dict."""
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "")
        if chat_id and text:
            return chat_id, text
        return None

