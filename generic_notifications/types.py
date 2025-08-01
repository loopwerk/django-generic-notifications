from abc import ABC
from typing import TYPE_CHECKING, Type

from .channels import EmailChannel, NotificationChannel
from .frequencies import DailyFrequency, NotificationFrequency, RealtimeFrequency
from .registry import registry

if TYPE_CHECKING:
    from .models import Notification


class NotificationType(ABC):
    """
    Represents a type of notification that can be sent to users.
    """

    key: str
    name: str
    description: str
    default_email_frequency: Type[NotificationFrequency] = DailyFrequency
    required_channels: list[Type[NotificationChannel]] = []

    def __str__(self) -> str:
        return self.name

    @classmethod
    def should_save(cls, notification: "Notification") -> bool:
        """
        A hook to prevent the saving of a new notification. You can use
        this hook to find similar (unread) notifications and then instead
        of creating this new notification, update the existing notification
        with a `count` property (stored in the `metadata` field).
        The `get_subject` or `get_text` methods can then use this `count`
        to dynamically change the text from "you received a comment" to
        "you received two comments", for example.
        """
        return True

    def get_subject(self, notification: "Notification") -> str:
        """
        Generate dynamic subject based on notification data.
        Override this in subclasses for custom behavior.
        """
        return ""

    def get_text(self, notification: "Notification") -> str:
        """
        Generate dynamic text based on notification data.
        Override this in subclasses for custom behavior.
        """
        return ""


def register(cls: Type[NotificationType]) -> Type[NotificationType]:
    """
    Decorator that registers a NotificationType subclass.

    Usage:
        @register
        class CommentNotificationType(NotificationType):
            key = "comment_notification"
            name = "Comments"
            description = "You received a comment"

            def get_subject(self, notification):
                return f"{notification.actor.name} commented on your article"
    """
    # Register the class
    registry.register_type(cls)

    # Return the class unchanged
    return cls


@register
class SystemMessage(NotificationType):
    key = "system_message"
    name = "System Message"
    description = "Important system notifications"
    default_email_frequency = RealtimeFrequency
    required_channels = [EmailChannel]

    def get_subject(self, notification: "Notification") -> str:
        """Generate subject for system messages."""
        if notification.subject:
            return notification.subject
        return f"System Message: {self.name}"

    def get_text(self, notification: "Notification") -> str:
        """Generate text for system messages."""
        if notification.text:
            return notification.text
        return self.description or f"You have a new {self.name.lower()} notification"
