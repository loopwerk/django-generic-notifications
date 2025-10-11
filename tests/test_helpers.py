"""Shared test helpers for django-generic-notifications tests"""

from django.contrib.auth import get_user_model

from generic_notifications.channels import EmailChannel, WebsiteChannel
from generic_notifications.models import Notification, NotificationChannel

User = get_user_model()


def create_notification_with_channels(user, channels=None, **kwargs):
    """
    Helper to create notification with the new model structure.

    Args:
        user: User instance to be the recipient
        channels: List of channel keys. Defaults to [website, email]
        **kwargs: Additional fields for the Notification model

    Returns:
        Notification instance with associated channels
    """
    if channels is None:
        channels = [WebsiteChannel.key, EmailChannel.key]

    defaults = {
        "recipient": user,
        "notification_type": "test_type",  # Default test type
    }
    defaults.update(kwargs)

    notification = Notification.objects.create(**defaults)

    # Create NotificationChannel entries
    for channel in channels:
        NotificationChannel.objects.create(notification=notification, channel=channel)

    return notification
