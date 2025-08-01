import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

if TYPE_CHECKING:
    from .types import NotificationType


def send_notification(recipient: Any, notification_type: "type[NotificationType]", actor=None, target=None, **kwargs):
    """
    Send a notification to a user through all registered channels.

    Args:
        recipient: User to send notification to
        notification_type: Type of notification (must be registered in registry)
        actor: User who triggered the notification (optional)
        target: Object the notification is about (optional)
        **kwargs: Additional fields for the notification (subject, text, url, metadata)

    Returns:
        Notification instance

    Raises:
        ValueError: If notification_type is not registered
    """
    from .models import Notification
    from .registry import registry

    # Validate notification type is registered
    try:
        registry.get_type(notification_type.key)
    except KeyError:
        available_types = [t.key for t in registry.get_all_types()]
        if available_types:
            raise ValueError(
                f"Notification type '{notification_type}' not registered. Available types: {available_types}"
            )
        else:
            raise ValueError(
                f"Notification type '{notification_type}' not registered. No notification types are currently registered."
            )

    # Determine which channels are enabled for this user/notification type
    enabled_channels = []
    enabled_channel_instances = []
    for channel_instance in registry.get_all_channels():
        if channel_instance.is_enabled(recipient, notification_type.key):
            enabled_channels.append(channel_instance.key)
            enabled_channel_instances.append(channel_instance)

    # Don't create notification if no channels are enabled
    if not enabled_channels:
        return None

    # Create the notification record with enabled channels
    notification = Notification(
        recipient=recipient,
        notification_type=notification_type.key,
        actor=actor,
        target=target,
        channels=enabled_channels,
        **kwargs,
    )

    # Use transaction to ensure atomicity when checking/updating existing notifications
    with transaction.atomic():
        if notification_type.should_save(notification):
            notification.save()

            # Process through enabled channels only
            for channel_instance in enabled_channel_instances:
                try:
                    channel_instance.process(notification)
                except Exception as e:
                    # Log error but don't crash - other channels should still work
                    logger = logging.getLogger(__name__)
                    logger.error(
                        f"Channel {channel_instance.key} failed to process notification {notification.id}: {e}"
                    )

            return notification
