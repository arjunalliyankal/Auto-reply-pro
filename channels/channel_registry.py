from channels.base import BaseChannel
from channels.telegram_channel import TelegramChannel
from channels.gmail_channel import GmailChannel


def get_active_channels(
    use_telegram: bool,
    telegram_token: str,
    use_gmail: bool,
    gmail_creds_path: str,
) -> list[BaseChannel]:
    """
    Dynamically builds and returns a list of enabled channel instances.

    Args:
        use_telegram: Toggle for Telegram.
        telegram_token: Telegram Bot token string.
        use_gmail: Toggle for Gmail.
        gmail_creds_path: Path to Gmail OAuth2 credentials JSON.

    Returns:
        List of instantiated BaseChannel objects.
    """
    channels: list[BaseChannel] = []

    if use_telegram and telegram_token:
        channels.append(TelegramChannel(bot_token=telegram_token))

    if use_gmail and gmail_creds_path:
        try:
            channels.append(GmailChannel(creds_path=gmail_creds_path))
        except Exception as e:
            print(f"[ChannelRegistry] Failed to load GmailChannel: {e}")

    return channels
