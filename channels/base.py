from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """Abstract interface that all channels must implement."""

    @abstractmethod
    def get_messages(self) -> list[dict]:
        """Fetch new/unread messages. Returns list of raw message dicts."""
        ...

    @abstractmethod
    def send_reply(self, *args, **kwargs) -> None:
        """Send a reply back through the channel."""
        ...
