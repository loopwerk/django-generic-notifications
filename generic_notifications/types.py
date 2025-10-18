from abc import ABC
from typing import TYPE_CHECKING, Any, Type

from .channels import BaseChannel, EmailChannel
from .frequencies import BaseFrequency, DailyFrequency, RealtimeFrequency
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
    default_frequency: Type[BaseFrequency] = DailyFrequency
    required_channels: list[Type[BaseChannel]] = []
    forbidden_channels: list[Type[BaseChannel]] = []

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

    @classmethod
    def set_frequency(cls, user: Any, frequency: Type[BaseFrequency]) -> None:
        """
        Set the delivery frequency for this notification type for a user.

        Args:
            user: The user to set the frequency for
            frequency: BaseFrequency class
        """
        from .models import NotificationFrequency

        NotificationFrequency.objects.update_or_create(
            user=user, notification_type=cls.key, defaults={"frequency": frequency.key}
        )

    @classmethod
    def get_frequency(cls, user: Any) -> Type[BaseFrequency]:
        """
        Get the delivery frequency for this notification type for a user.

        Args:
            user: The user to get the frequency for

        Returns:
            BaseFrequency class (either user preference or default)
        """
        from .models import NotificationFrequency

        try:
            user_frequency = NotificationFrequency.objects.get(user=user, notification_type=cls.key)
            return registry.get_frequency(user_frequency.frequency)
        except NotificationFrequency.DoesNotExist:
            return cls.default_frequency

    @classmethod
    def reset_frequency_to_default(cls, user: Any) -> None:
        """
        Reset the delivery frequency to default for this notification type for a user.

        Args:
            user: The user to reset the frequency for
        """
        from .models import NotificationFrequency

        NotificationFrequency.objects.filter(user=user, notification_type=cls.key).delete()

    @classmethod
    def get_enabled_channels(cls, user: Any) -> list[Type[BaseChannel]]:
        """
        Get all enabled channels for this notification type for a user.
        This is more efficient than calling is_channel_enabled for each channel individually.

        Args:
            user: User instance

        Returns:
            List of enabled BaseChannel classes
        """
        from .models import DisabledNotificationTypeChannel

        # Get all disabled channel keys for this user/notification type in one query
        disabled_channel_keys = set(
            DisabledNotificationTypeChannel.objects.filter(user=user, notification_type=cls.key).values_list(
                "channel", flat=True
            )
        )

        # Get all forbidden channel keys
        forbidden_channel_keys = {channel_cls.key for channel_cls in cls.forbidden_channels}

        # Filter out disabled and forbidden channels
        enabled_channels = []
        for channel_cls in registry.get_all_channels():
            if channel_cls.key not in disabled_channel_keys and channel_cls.key not in forbidden_channel_keys:
                enabled_channels.append(channel_cls)

        return enabled_channels

    @classmethod
    def is_channel_enabled(cls, user: Any, channel: Type[BaseChannel]) -> bool:
        """
        Check if a channel is enabled for this notification type for a user.

        Args:
            user: User instance
            channel: BaseChannel class

        Returns:
            True if channel is enabled, False if disabled
        """
        from .models import DisabledNotificationTypeChannel

        return not DisabledNotificationTypeChannel.objects.filter(
            user=user, notification_type=cls.key, channel=channel.key
        ).exists()

    @classmethod
    def disable_channel(cls, user: Any, channel: Type[BaseChannel]) -> None:
        """
        Disable a channel for this notification type for a user.

        Args:
            user: User instance
            channel: BaseChannel class
        """
        from .models import DisabledNotificationTypeChannel

        DisabledNotificationTypeChannel.objects.get_or_create(user=user, notification_type=cls.key, channel=channel.key)

    @classmethod
    def enable_channel(cls, user: Any, channel: Type[BaseChannel]) -> None:
        """
        Enable a channel for this notification type for a user.

        Args:
            user: User instance
            channel: BaseChannel class
        """
        from .models import DisabledNotificationTypeChannel

        DisabledNotificationTypeChannel.objects.filter(
            user=user, notification_type=cls.key, channel=channel.key
        ).delete()


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
    default_frequency = RealtimeFrequency
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
