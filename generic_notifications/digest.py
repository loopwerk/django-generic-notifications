import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser

from .frequencies import BaseFrequency
from .models import Notification
from .registry import registry
from .types import NotificationType

User = get_user_model()

logger = logging.getLogger(__name__)


def send_notification_digests(frequency: type[BaseFrequency], dry_run: bool = False) -> int:
    """
    Send notification digests for a specific frequency across all channels that support digests.

    Args:
        frequency: The frequency class to process (e.g., DailyFrequency, WeeklyFrequency)
        dry_run: If True, don't actually send notifications, just log what would be sent

    Returns:
        Total number of digests sent across all channels

    Raises:
        ValueError: If the frequency is realtime (not a digest frequency)
    """
    if frequency.is_realtime:
        raise ValueError(f"Frequency '{frequency.key}' is realtime, not a digest frequency")

    # Get all channels that support digest functionality
    digest_channels = [channel_cls() for channel_cls in registry.get_all_channels() if channel_cls.supports_digest]

    if not digest_channels:
        logger.warning("No channels support digest functionality")
        return 0

    logger.info(f"Processing {frequency.name} digests for {len(digest_channels)} channel(s)...")

    all_notification_types = registry.get_all_types()
    total_digests_sent = 0

    for channel in digest_channels:
        channel_digests_sent = _send_digest_for_channel(channel, frequency, all_notification_types, dry_run)
        total_digests_sent += channel_digests_sent

        if dry_run:
            logger.info(f"  {channel.name}: Would have sent {channel_digests_sent} digests")
        else:
            logger.info(f"  {channel.name}: Sent {channel_digests_sent} digests")

    return total_digests_sent


def _send_digest_for_channel(
    channel: Any,
    frequency_cls: type[BaseFrequency],
    all_notification_types: list[type[NotificationType]],
    dry_run: bool,
) -> int:
    """
    Send digests for a specific channel and frequency.

    Args:
        channel: Channel instance to send digests through
        frequency_cls: Frequency class being processed
        all_notification_types: List of all registered notification types
        dry_run: If True, don't actually send

    Returns:
        Number of digests sent for this channel
    """
    # Find all users who have unsent, unread notifications for this channel
    users_with_notifications = User.objects.filter(
        notifications__read__isnull=True,
        notifications__channels__channel=channel.key,
        notifications__channels__sent_at__isnull=True,
    ).distinct()

    digests_sent = 0

    for user in users_with_notifications:
        # Determine which notification types should use this frequency for this user
        relevant_types = _get_notification_types_for_frequency(user, frequency_cls, all_notification_types)

        if not relevant_types:
            continue

        # Get unsent notifications for these types
        # Exclude read notifications - don't send what user already saw on website
        relevant_type_keys = [nt.key for nt in relevant_types]
        notifications = Notification.objects.filter(
            recipient=user,
            notification_type__in=relevant_type_keys,
            read__isnull=True,
            channels__channel=channel.key,
            channels__sent_at__isnull=True,
        ).order_by("-added")

        if notifications.exists():
            logger.debug(
                f"    User {user.email}: {notifications.count()} notifications for {frequency_cls.name} digest"
            )

            if not dry_run:
                channel.send_digest(notifications, frequency_cls)

            digests_sent += 1

            # List notification subjects for debugging
            for notification in notifications[:3]:  # Show first 3
                logger.debug(f"      - {notification.subject or notification.text[:30]}")
            if notifications.count() > 3:
                logger.debug(f"      ... and {notifications.count() - 3} more")

    return digests_sent


def _get_notification_types_for_frequency(
    user: AbstractUser,
    wanted_frequency: type[BaseFrequency],
    all_notification_types: list[type[NotificationType]],
) -> list[type[NotificationType]]:
    """
    Get all notification types that should use this frequency for the given user.
    This includes both explicit preferences and types that default to this frequency.
    Since notifications are only created for enabled channels, we don't need to check is_enabled.

    Args:
        user: The user to check preferences for
        wanted_frequency: The frequency to filter by (e.g. DailyFrequency, RealtimeFrequency)
        all_notification_types: List of all registered notification type classes

    Returns:
        List of notification type classes that use this frequency for this user
    """
    relevant_types: list[type[NotificationType]] = []

    for notification_type in all_notification_types:
        user_frequency = notification_type.get_frequency(user)
        if user_frequency.key == wanted_frequency.key:
            relevant_types.append(notification_type)

    return relevant_types
