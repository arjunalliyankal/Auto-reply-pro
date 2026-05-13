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
                params={"offset": self.offset, "timeout": 10},
                timeout=15,
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
        """Send a text reply to a Telegram chat."""
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
        except Exception as e:
            print(f"[Telegram] Error sending reply: {e}")

    def parse_message(self, update: dict) -> tuple[int, str] | None:
        """Extract (chat_id, text) from a raw update dict."""
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "")
        if chat_id and text:
            return chat_id, text
        return None
