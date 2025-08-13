import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Type

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.template.defaultfilters import pluralize
from django.template.loader import render_to_string
from django.utils import timezone

from .frequencies import NotificationFrequency
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
        # Get notification type class from key
        notification_type_cls = registry.get_type(notification.notification_type)
        frequency_cls = notification_type_cls.get_email_frequency(notification.recipient)

        # Send immediately if realtime, otherwise leave for digest
        if frequency_cls and frequency_cls.is_realtime:
            self.send_email_now(notification)

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
                # Fallback to notification's text with URL if available
                text_message = notification.get_text()
                absolute_url = notification.get_absolute_url()
                if absolute_url:
                    text_message += f"\n{absolute_url}"

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
        cls, user: Any, notifications: "QuerySet[Notification]", frequency: type[NotificationFrequency] | None = None
    ):
        """
        Send a digest email to a specific user with specific notifications.
        This method is used by the management command.

        Args:
            user: User instance
            notifications: QuerySet of notifications to include in digest
            frequency: The frequency for template context
        """
        if not notifications.exists():
            return

        try:
            # Group notifications by type for better digest formatting
            notifications_by_type: dict[str, list["Notification"]] = {}
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

            notifications_count = notifications.count()

            # Load subject
            try:
                subject = render_to_string(subject_template, context).strip()
            except Exception:
                # Fallback subject
                frequency_name = frequency.name if frequency else "Digest"
                subject = f"{frequency_name} - {notifications_count} new notification{pluralize(notifications_count)}"

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
                message_lines = [f"You have {notifications_count} new notification{pluralize(notifications_count)}:\n"]
                for notification in notifications[:10]:  # Limit to first 10
                    message_lines.append(f"- {notification.get_text()}")
                    absolute_url = notification.get_absolute_url()
                    if absolute_url:
                        message_lines.append(f"  {absolute_url}")
                if notifications_count > 10:
                    message_lines.append(f"... and {notifications_count - 10} more")
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
