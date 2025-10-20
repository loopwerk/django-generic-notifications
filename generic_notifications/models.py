from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .channels import BaseChannel, WebsiteChannel
from .registry import registry

User = get_user_model()


class NotificationQuerySet(models.QuerySet):
    """Custom QuerySet for optimized notification queries"""

    def prefetch(self):
        """Prefetch related objects"""
        return self.select_related("recipient", "actor")

    def for_channel(self, channel: type[BaseChannel] = WebsiteChannel):
        """Filter notifications by channel"""
        return self.filter(channels__channel=channel.key)

    def unread(self):
        """Filter only unread notifications"""
        return self.filter(read__isnull=True)


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
    object_id = models.CharField(max_length=36, null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    # Flexible metadata for any extra data
    metadata = models.JSONField(default=dict, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["recipient", "read"], name="notification_unread_idx"),
            models.Index(fields=["recipient", "added"], name="notification_recipient_idx"),
            models.Index(fields=["content_type", "object_id"], name="notification_target_idx"),
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
            notification_type_cls = registry.get_type(self.notification_type)
            notification_type = notification_type_cls()
            return notification_type.get_subject(self) or notification_type.description
        except KeyError:
            return f"Notification: {self.notification_type}"

    def get_text(self) -> str:
        """Get the text, using dynamic generation if not stored."""
        if self.text:
            return self.text

        # Get the notification type and use its dynamic generation
        try:
            notification_type_cls = registry.get_type(self.notification_type)
            notification_type = notification_type_cls()
            return notification_type.get_text(self)
        except KeyError:
            return "You have a new notification"

    def get_channels(self) -> list[str]:
        """Get all channels this notification is configured for."""
        return list(self.channels.values_list("channel", flat=True))

    def is_sent_on_channel(self, channel: type["BaseChannel"]) -> bool:
        """Check if notification was sent on a specific channel."""
        return self.channels.filter(channel=channel.key, sent_at__isnull=False).exists()

    def mark_sent_on_channel(self, channel: type["BaseChannel"]) -> None:
        """Mark notification as sent on a specific channel."""
        self.channels.filter(channel=channel.key).update(sent_at=timezone.now())

    @property
    def is_read(self) -> bool:
        return self.read is not None

    def get_absolute_url(self) -> str:
        """
        Get the absolute URL for this notification.
        If the URL is already absolute (starts with http:// or https://), return as-is.
        Otherwise, prepend the base URL from settings if available.
        """
        if not self.url:
            return ""

        # If already absolute, return as-is
        if self.url.startswith(("http://", "https://")):
            return self.url

        # Get base URL from settings, with fallback
        base_url = getattr(settings, "NOTIFICATION_BASE_URL", "")

        if not base_url:
            # Try common alternatives
            base_url = getattr(settings, "BASE_URL", "")
            if not base_url:
                base_url = getattr(settings, "SITE_URL", "")

        if not base_url and "django.contrib.sites" in settings.INSTALLED_APPS:
            # Try the Sites framework
            from django.contrib.sites.models import Site

            try:
                base_url = Site.objects.get_current().domain
            except Site.DoesNotExist:
                pass

        if base_url:
            # Add protocol if missing
            if not base_url.startswith(("http://", "https://")):
                protocol = "http" if settings.DEBUG else "https"
                base_url = f"{protocol}://{base_url}"

            # Ensure base URL doesn't end with slash and relative URL doesn't start with slash
            base_url = base_url.rstrip("/")
            relative_url = self.url.lstrip("/")
            return f"{base_url}/{relative_url}"

        # No base URL configured, return relative URL
        return self.url


class NotificationChannel(models.Model):
    """
    Tracks which channels a notification should be sent through and their delivery status.
    """

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="channels")
    channel = models.CharField(max_length=20)  # e.g., 'email', 'website', etc.
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["notification", "channel"]
        indexes = [
            models.Index(fields=["notification", "channel", "sent_at"]),
            models.Index(fields=["channel", "sent_at"]),  # For digest queries
        ]

    def __str__(self):
        status = "sent" if self.sent_at else "pending"
        return f"{self.notification} - {self.channel} ({status})"


class NotificationTypeChannelPreference(models.Model):
    """
    Stores explicit user preferences for notification type/channel combinations.
    If no row exists, the default behavior (from NotificationType.default_channels
    or BaseChannel.enabled_by_default) is used.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_type_channel_preferences")
    notification_type = models.CharField(max_length=50)
    channel = models.CharField(max_length=20)
    enabled = models.BooleanField(default=False)

    class Meta:
        unique_together = ["user", "notification_type", "channel"]

    def clean(self):
        try:
            notification_type_cls = registry.get_type(self.notification_type)
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
        if not self.enabled:
            required_channel_keys = [cls.key for cls in notification_type_cls.required_channels]
            if self.channel in required_channel_keys:
                raise ValidationError(
                    f"Cannot disable {self.channel} channel for {notification_type_cls.name} - this channel is required"
                )

        # Check if trying to enable a forbidden channel
        if self.enabled:
            forbidden_channel_keys = [cls.key for cls in notification_type_cls.forbidden_channels]
            if self.channel in forbidden_channel_keys:
                raise ValidationError(
                    f"Cannot enable {self.channel} channel for {notification_type_cls.name} - this channel is forbidden"
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
        status = "enabled" if self.enabled else "disabled"
        return f"{self.user} {status} {self.notification_type} on {self.channel}"


class NotificationFrequencyPreference(models.Model):
    """
    Delivery frequency preference per notification type.
    This applies to all channels that support the chosen frequency.
    Default is `NotificationType.default_frequency` if no row exists.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_frequency_preferences")
    notification_type = models.CharField(max_length=50)
    frequency = models.CharField(max_length=20)

    class Meta:
        unique_together = ["user", "notification_type"]
        verbose_name_plural = "Notification frequency preferences"

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
