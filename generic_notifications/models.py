from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .channels import NotificationChannel, WebsiteChannel
from .registry import registry

User = get_user_model()


class NotificationQuerySet(models.QuerySet):
    """Custom QuerySet for optimized notification queries"""

    def prefetch(self):
        """Prefetch related objects"""
        return self.select_related("recipient", "actor")

    def for_channel(self, channel: type[NotificationChannel] = WebsiteChannel):
        """Filter notifications by channel"""
        return self.filter(channels__icontains=f'"{channel.key}"')

    def unread(self):
        """Filter only unread notifications"""
        return self.filter(read__isnull=True)


class DisabledNotificationTypeChannel(models.Model):
    """
    If a row exists here, that notification type/channel combination is DISABLED for the user.
    By default (no row), all notifications are enabled on all channels.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="disabled_notification_type_channels")
    notification_type = models.CharField(max_length=50)
    channel = models.CharField(max_length=20)

    class Meta:
        unique_together = ["user", "notification_type", "channel"]

    def clean(self):
        try:
            notification_type_obj = registry.get_type(self.notification_type)
        except KeyError:
            available_types = [t.key for t in registry.get_all_types()]
            if available_types:
                raise ValidationError(
                    f"Unknown notification type: {self.notification_type}. Available types: {available_types}"
                )
            else:
                raise ValidationError(
                    f"Unknown notification type: {self.notification_type}. No notification types are currently registered."
                )

        # Check if trying to disable a required channel
        required_channel_keys = [cls.key for cls in notification_type_obj.required_channels]
        if self.channel in required_channel_keys:
            raise ValidationError(
                f"Cannot disable {self.channel} channel for {notification_type_obj.name} - this channel is required"
            )

        try:
            registry.get_channel(self.channel)
        except KeyError:
            available_channels = [c.key for c in registry.get_all_channels()]
            if available_channels:
                raise ValidationError(f"Unknown channel: {self.channel}. Available channels: {available_channels}")
            else:
                raise ValidationError(f"Unknown channel: {self.channel}. No channels are currently registered.")

    def __str__(self) -> str:
        return f"{self.user} disabled {self.notification_type} on {self.channel}"


class EmailFrequency(models.Model):
    """
    Email delivery frequency preference per notification type.
    Default is `NotificationType.default_email_frequency` if no row exists.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_frequencies")
    notification_type = models.CharField(max_length=50)
    frequency = models.CharField(max_length=20)

    class Meta:
        unique_together = ["user", "notification_type"]

    def clean(self):
        if self.notification_type:
            try:
                registry.get_type(self.notification_type)
            except KeyError:
                available_types = [t.key for t in registry.get_all_types()]
                if available_types:
                    raise ValidationError(
                        f"Unknown notification type: {self.notification_type}. Available types: {available_types}"
                    )
                else:
                    raise ValidationError(
                        f"Unknown notification type: {self.notification_type}. No notification types are currently registered."
                    )

        if self.frequency:
            try:
                registry.get_frequency(self.frequency)
            except KeyError:
                available_frequencies = [f.key for f in registry.get_all_frequencies()]
                if available_frequencies:
                    raise ValidationError(
                        f"Unknown frequency: {self.frequency}. Available frequencies: {available_frequencies}"
                    )
                else:
                    raise ValidationError(
                        f"Unknown frequency: {self.frequency}. No frequencies are currently registered."
                    )

    def __str__(self) -> str:
        return f"{self.user} - {self.notification_type}: {self.frequency}"


class Notification(models.Model):
    """
    A specific notification instance for a user
    """

    # Core fields
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=50)
    added = models.DateTimeField(auto_now_add=True)
    read = models.DateTimeField(null=True, blank=True)

    # Content fields
    subject = models.CharField(max_length=255, blank=True)
    text = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)

    # Related data
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications_sent")

    # Generic relation to link to any object (article, comment, etc)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    # Email tracking
    email_sent_at = models.DateTimeField(null=True, blank=True)

    # Channels this notification is enabled for
    channels = models.JSONField(default=list, blank=True)

    # Flexible metadata for any extra data
    metadata = models.JSONField(default=dict, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        indexes = [
            GinIndex(fields=["channels"], name="notification_channels_gin"),
            models.Index(fields=["recipient", "read", "channels"], name="notification_unread_channel"),
            models.Index(fields=["recipient", "channels"], name="notification_recipient_channel"),
            models.Index(
                fields=["recipient", "email_sent_at", "read", "channels"], name="notification_user_email_digest"
            ),
        ]
        ordering = ["-added"]

    def clean(self) -> None:
        if self.notification_type:
            try:
                registry.get_type(self.notification_type)
            except KeyError:
                available_types = [t.key for t in registry.get_all_types()]
                if available_types:
                    raise ValidationError(
                        f"Unknown notification type: {self.notification_type}. Available types: {available_types}"
                    )
                else:
                    raise ValidationError(
                        f"Unknown notification type: {self.notification_type}. No notification types are currently registered."
                    )

    def __str__(self) -> str:
        return f"{self.notification_type} for {self.recipient}"

    def mark_as_read(self) -> None:
        """Mark this notification as read"""
        if not self.read:
            self.read = timezone.now()
            self.save(update_fields=["read"])

    def mark_as_unread(self) -> None:
        """Mark this notification as unread"""
        if self.read:
            self.read = None
            self.save(update_fields=["read"])

    def get_subject(self) -> str:
        """Get the subject, using dynamic generation if not stored."""
        if self.subject:
            return self.subject

        # Get the notification type and use its dynamic generation
        try:
            notification_type = registry.get_type(self.notification_type)
            return notification_type.get_subject(self) or notification_type.description
        except KeyError:
            return f"Notification: {self.notification_type}"

    def get_text(self) -> str:
        """Get the text, using dynamic generation if not stored."""
        if self.text:
            return self.text

        # Get the notification type and use its dynamic generation
        try:
            notification_type = registry.get_type(self.notification_type)
            return notification_type.get_text(self)
        except KeyError:
            return "You have a new notification"

    @property
    def is_read(self) -> bool:
        return self.read is not None
