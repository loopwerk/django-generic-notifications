import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Type

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.template.loader import render_to_string
from django.utils import timezone

from .frequencies import DailyFrequency, NotificationFrequency
from .registry import registry

if TYPE_CHECKING:
    from .models import Notification


class NotificationChannel(ABC):
    """
    Base class for all notification channels.
    """

    key: str
    name: str

    @abstractmethod
    def process(self, notification: "Notification") -> None:
        """
        Process a notification through this channel.

        Args:
            notification: Notification instance to process
        """
        pass

    def is_enabled(self, user: Any, notification_type: str) -> bool:
        """
        Check if user has this channel enabled for this notification type.

        Args:
            user: User instance
            notification_type: Notification type key

        Returns:
            bool: True if enabled (default), False if disabled
        """
        from .models import DisabledNotificationTypeChannel

        return not DisabledNotificationTypeChannel.objects.filter(
            user=user, notification_type=notification_type, channel=self.key
        ).exists()


def register(cls: Type[NotificationChannel]) -> Type[NotificationChannel]:
    """
    Decorator that registers a NotificationChannel subclass.

    Usage:
        @register
        class EmailChannel(NotificationChannel):
            key = "email"
            name = "Email"

            def process(self, notification):
                # Send email
    """
    # Register the class
    registry.register_channel(cls)

    # Return the class unchanged
    return cls


@register
class WebsiteChannel(NotificationChannel):
    """
    Channel for displaying notifications on the website.
    Notifications are stored in the database and displayed in the UI.
    """

    key = "website"
    name = "Website"

    def process(self, notification: "Notification") -> None:
        """
        Website notifications are just stored in DB - no additional processing needed.
        The notification was already created before channels are processed.
        """
        pass


@register
class EmailChannel(NotificationChannel):
    """
    Channel for sending notifications via email.
    Supports both realtime delivery and daily digest batching.
    """

    key = "email"
    name = "Email"

    def process(self, notification: "Notification") -> None:
        """
        Process email notification based on user's frequency preference.

        Args:
            notification: Notification instance to process
        """
        frequency = self.get_frequency(notification.recipient, notification.notification_type)

        # Send immediately if realtime, otherwise leave for digest
        if frequency and frequency.is_realtime:
            self.send_email_now(notification)

    def get_frequency(self, user: Any, notification_type: str) -> NotificationFrequency:
        """
        Get the user's email frequency preference for this notification type.

        Args:
            user: User instance
            notification_type: Notification type key

        Returns:
            NotificationFrequency: NotificationFrequency instance (defaults to notification type's default)
        """
        from .models import EmailFrequency

        try:
            email_frequency = EmailFrequency.objects.get(user=user, notification_type=notification_type)
            return registry.get_frequency(email_frequency.frequency)
        except (EmailFrequency.DoesNotExist, KeyError):
            # Get the notification type's default frequency
            try:
                notification_type_obj = registry.get_type(notification_type)
                return notification_type_obj.default_email_frequency()
            except (KeyError, AttributeError):
                # Fallback to realtime if notification type not found or no default
                return DailyFrequency()

    def send_email_now(self, notification: "Notification") -> None:
        """
        Send an individual email notification immediately.

        Args:
            notification: Notification instance to send
        """
        try:
            context = {
                "notification": notification,
                "user": notification.recipient,
                "actor": notification.actor,
                "target": notification.target,
            }

            subject_template = f"notifications/email/realtime/{notification.notification_type}_subject.txt"
            html_template = f"notifications/email/realtime/{notification.notification_type}.html"
            text_template = f"notifications/email/realtime/{notification.notification_type}.txt"

            # Load subject
            try:
                subject = render_to_string(subject_template, context).strip()
            except Exception:
                # Fallback to notification's subject
                subject = notification.get_subject()

            # Load HTML message
            try:
                html_message = render_to_string(html_template, context)
            except Exception:
                html_message = None

            # Load plain text message
            text_message: str
            try:
                text_message = render_to_string(text_template, context)
            except Exception:
                # Fallback to notification's text
                text_message = notification.get_text()

            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.recipient.email],
                html_message=html_message,
                fail_silently=False,
            )

            # Mark as sent
            notification.email_sent_at = timezone.now()
            notification.save(update_fields=["email_sent_at"])

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send email for notification {notification.id}: {e}")

    @classmethod
    def send_digest_emails(
        cls, user: Any, notifications: "QuerySet[Notification]", frequency: NotificationFrequency | None = None
    ):
        """
        Send a digest email to a specific user with specific notifications.
        This method is used by the management command.

        Args:
            user: User instance
            notifications: QuerySet of notifications to include in digest
            frequency: The frequency for template context
        """
        from .models import Notification

        if not notifications.exists():
            return

        try:
            # Group notifications by type for better digest formatting
            notifications_by_type: dict[str, list[Notification]] = {}
            for notification in notifications:
                if notification.notification_type not in notifications_by_type:
                    notifications_by_type[notification.notification_type] = []
                notifications_by_type[notification.notification_type].append(notification)

            context = {
                "user": user,
                "notifications": notifications,
                "notifications_by_type": notifications_by_type,
                "count": notifications.count(),
                "frequency": frequency,
            }

            subject_template = "notifications/email/digest/subject.txt"
            html_template = "notifications/email/digest/message.html"
            text_template = "notifications/email/digest/message.txt"

            # Load subject
            try:
                subject = render_to_string(subject_template, context).strip()
            except Exception:
                # Fallback subject
                frequency_name = frequency.name if frequency else "Digest"
                subject = f"{frequency_name} - {notifications.count()} new notifications"

            # Load HTML message
            try:
                html_message = render_to_string(html_template, context)
            except Exception:
                html_message = None

            # Load plain text message
            text_message: str
            try:
                text_message = render_to_string(text_template, context)
            except Exception:
                # Fallback if template doesn't exist
                message_lines = [f"You have {notifications.count()} new notifications:"]
                for notification in notifications[:10]:  # Limit to first 10
                    message_lines.append(f"- {notification.get_subject()}")
                if notifications.count() > 10:
                    message_lines.append(f"... and {notifications.count() - 10} more")
                text_message = "\n".join(message_lines)

            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

            # Mark all as sent
            notifications.update(email_sent_at=timezone.now())

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send digest email for user {user.id}: {e}")
