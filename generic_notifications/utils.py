from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from .channels import BaseChannel, WebsiteChannel


def mark_notifications_as_read(user: Any, notification_ids: list[int] | None = None) -> None:
    """
    Mark notifications as read for a user.

    Args:
        user: User instance
        notification_ids: List of notification IDs to mark as read.
                         If None, marks all unread notifications as read.
    """
    queryset = user.notifications.filter(read__isnull=True)

    if notification_ids:
        queryset = queryset.filter(id__in=notification_ids)

    queryset.update(read=timezone.now())


def get_unread_count(user: Any, channel: type[BaseChannel] = WebsiteChannel) -> int:
    """
    Get count of unread notifications for a user, filtered by channel.

    Args:
        user: User instance
        channel: Channel to filter by (e.g., WebsiteChannel, EmailChannel)

    Returns:
        Count of unread notifications for the specified channel
    """
    return user.notifications.filter(read__isnull=True).for_channel(channel).count()


def get_notifications(
    user: Any, channel: type[BaseChannel] = WebsiteChannel, unread_only: bool = False, limit: int | None = None
) -> QuerySet:
    """
    Get notifications for a user, filtered by channel.

    Args:
        user: User instance
        channel: Channel to filter by (e.g., WebsiteChannel, EmailChannel)
        unread_only: If True, only return unread notifications
        limit: Maximum number of notifications to return

    Returns:
        QuerySet of Notification objects
    """
    queryset = user.notifications.prefetch().for_channel(channel)

    if unread_only:
        queryset = queryset.unread()

    if limit:
        queryset = queryset[:limit]

    return queryset
