import logging
from abc import ABC
from typing import TYPE_CHECKING, Type

from django.conf import settings
from django.core.mail import send_mail as django_send_mail
from django.db.models import QuerySet
from django.template.defaultfilters import pluralize
from django.template.loader import render_to_string, select_template

from .frequencies import BaseFrequency
from .registry import registry

if TYPE_CHECKING:
    from .models import Notification


class BaseChannel(ABC):
    """
    Base class for all notification channels.
    """

    key: str
    name: str
    supports_realtime: bool = True
    supports_digest: bool = False
    enabled_by_default: bool = True

    @classmethod
    def should_send(cls, notification: "Notification") -> bool:
        """
        Check if this channel can send the given notification.
        Override in subclasses to add channel-specific validation.

        Args:
            notification: Notification instance to check

        Returns:
            bool: True if the channel can send this notification, False otherwise
        """
        return True

    def process(self, notification: "Notification") -> None:
        """
        Process a notification through this channel based on channel capabilities
        and user preferences. If the notification should be handled realtime,
        then call `send_now`. If it should be handled in a digest delivery,
        then do nothing, as the send_notification_digests function/command will
        pick it up.

        Args:
            notification: Notification instance to process
        """
        # Digest-only channels: never send immediately
        if self.supports_digest and not self.supports_realtime:
            return

        # Channels that support both: check user preference
        if self.supports_digest:
            # Get notification type class from key
            notification_type_cls = registry.get_type(notification.notification_type)
            frequency_cls = notification_type_cls.get_frequency(notification.recipient)

            # User prefers digest delivery (not realtime)
            if frequency_cls and not frequency_cls.is_realtime:
                return

        # Send immediately if channel supports realtime
        if self.supports_realtime:
            self.send_now(notification)

    def send_now(self, notification: "Notification") -> None:
        """
        Send a notification immediately through this channel.
        Override in subclasses that support realtime delivery.

        Args:
            notification: Notification instance to send
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support realtime sending")

    def send_digest(self, notifications: "QuerySet[Notification]", frequency: type[BaseFrequency]) -> None:
        """
        Send a digest with specific notifications.
        Override in subclasses that support digest delivery.

        Args:
            notifications: QuerySet of notifications to include in digest (must all have same recipient)
            frequency: The frequency for context
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support digest sending")


def register(cls: Type[BaseChannel]) -> Type[BaseChannel]:
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
class WebsiteChannel(BaseChannel):
    """
    Channel for displaying notifications on the website.
    Notifications are stored in the database and displayed in the UI.
    """

    key = "website"
    name = "Website"
    supports_realtime = True
    supports_digest = False

    def send_now(self, notification: "Notification") -> None:
        """
        Website notifications are just stored in DB - no additional processing needed.
        """
        pass


@register
class EmailChannel(BaseChannel):
    """
    Channel for sending notifications via email.
    Supports both realtime delivery and daily digest batching.
    """

    key = "email"
    name = "Email"
    supports_realtime = True
    supports_digest = True

    @classmethod
    def should_send(cls, notification: "Notification") -> bool:
        """
        Check if the recipient has an email address.

        Args:
            notification: Notification instance to check

        Returns:
            bool: True if the recipient has an email address, False otherwise
        """
        return bool(getattr(notification.recipient, "email", None))

    def send_now(self, notification: "Notification") -> None:
        """
        Send an individual email notification immediately.

        Args:
            notification: Notification instance to send
        """
        try:
            context = {
                "notification": notification,
                "user": notification.recipient,
                "recipient": notification.recipient,
                "actor": notification.actor,
                "target": notification.target,
            }

            subject_templates = [
                f"notifications/email/realtime/{notification.notification_type}_subject.txt",
                "notifications/email/realtime/subject.txt",
            ]
            html_templates = [
                f"notifications/email/realtime/{notification.notification_type}.html",
                "notifications/email/realtime/message.html",
            ]
            text_templates = [
                f"notifications/email/realtime/{notification.notification_type}.txt",
                "notifications/email/realtime/message.txt",
            ]

            # Load subject
            try:
                subject_template = select_template(subject_templates)
                subject = subject_template.render(context).strip()
            except Exception:
                # Fallback to notification's subject
                subject = notification.get_subject()

            # Load HTML message
            try:
                html_template = select_template(html_templates)
                html_message = html_template.render(context)
            except Exception:
                html_message = None

            # Load plain text message
            text_message: str
            try:
                text_template = select_template(text_templates)
                text_message = text_template.render(context)
            except Exception:
                # Fallback to notification's text with URL if available
                text_message = notification.get_text()
                absolute_url = notification.get_absolute_url()
                if absolute_url:
                    text_message += f"\n{absolute_url}"

            self.send_email(
                recipient=notification.recipient.email,
                subject=subject,
                text_message=text_message,
                html_message=html_message,
            )

            # Mark as sent
            notification.mark_sent_on_channel(self.__class__)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send email for notification {notification.id}: {e}")

    def send_digest(self, notifications: "QuerySet[Notification]", frequency: type[BaseFrequency]):
        """
        Send a digest email with specific notifications.
        This method is used by the management command.

        Args:
            notifications: QuerySet of notifications to include in digest (must all have same recipient)
            frequency: The frequency for template context
        """
        if not notifications.exists():
            return

        # Get user from first notification (all have same recipient)
        user = notifications.first().recipient

        try:
            # Group notifications by type for better digest formatting
            notifications_by_type: dict[str, list["Notification"]] = {}
            for notification in notifications:
                if notification.notification_type not in notifications_by_type:
                    notifications_by_type[notification.notification_type] = []
                notifications_by_type[notification.notification_type].append(notification)

            context = {
                "user": user,
                "recipient": user,
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
                subject = f"{frequency.name} - {notifications_count} new notification{pluralize(notifications_count)}"

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

            self.send_email(
                recipient=user.email,
                subject=subject,
                text_message=text_message,
                html_message=html_message,
            )

            # Mark all as sent
            for notification in notifications:
                notification.mark_sent_on_channel(self.__class__)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send digest email for user {user.id}: {e}")

    def send_email(self, recipient: str, subject: str, text_message: str, html_message: str | None = None) -> None:
        """
        Actually send the email. This method can be overridden by subclasses
        to use different email backends (e.g., Celery, different email services).

        Args:
            recipient: Email address of the recipient
            subject: Email subject
            text_message: Plain text email content
            html_message: HTML email content (optional)
        """
        django_send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_message,
            fail_silently=False,
        )
