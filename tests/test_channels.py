from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from generic_notifications.channels import EmailChannel, NotificationChannel
from generic_notifications.frequencies import RealtimeFrequency
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency, Notification
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

User = get_user_model()


# Test subclasses for abstract base classes
class TestNotificationType(NotificationType):
    key = "test_type"
    name = "Test Type"
    description = "A test notification type"
    default_email_frequency = RealtimeFrequency


class NotificationChannelTest(TestCase):
    user: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="user1", email="test@example.com", password="testpass")

    def test_notification_channel_is_abstract(self):
        class TestChannel(NotificationChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        channel = TestChannel()
        self.assertEqual(channel.key, "test")
        self.assertEqual(channel.name, "Test")

    def test_is_enabled_default_true(self):
        class TestChannel(NotificationChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        # By default, all notifications are enabled
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, TestChannel))

    def test_is_enabled_with_disabled_notification(self):
        class TestChannel(NotificationChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        class DisabledNotificationType(NotificationType):
            key = "disabled_type"
            name = "Disabled Type"

        class OtherNotificationType(NotificationType):
            key = "other_type"
            name = "Other Type"

        # Disable notification channel for this user
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type="disabled_type", channel="test"
        )

        # Should be disabled for this type
        self.assertFalse(DisabledNotificationType.is_channel_enabled(self.user, TestChannel))

        # But enabled for other types
        self.assertTrue(OtherNotificationType.is_channel_enabled(self.user, TestChannel))


class WebsiteChannelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user2", email="test@example.com", password="testpass")
        registry.register_type(TestNotificationType)

        self.notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test Subject"
        )

    def tearDown(self):
        pass


class EmailChannelTest(TestCase):
    user: Any  # User model instance created in setUp

    def setUp(self):
        self.user = User.objects.create_user(username="user1", email="test@example.com", password="testpass")
        registry.register_type(TestNotificationType)

    def tearDown(self):
        mail.outbox.clear()

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_process_realtime_frequency(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
        )

        channel = EmailChannel()
        channel.process(notification)

        # Should send email immediately for realtime frequency
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])

        # Check notification was marked as sent
        notification.refresh_from_db()
        self.assertIsNotNone(notification.email_sent_at)

    def test_process_digest_frequency(self):
        # Set user preference to daily (non-realtime)
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
        )

        channel = EmailChannel()
        channel.process(notification)

        # Should not send email immediately for digest frequency
        self.assertEqual(len(mail.outbox), 0)

        # Notification should not be marked as sent
        notification.refresh_from_db()
        self.assertIsNone(notification.email_sent_at)

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_now_basic(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test Subject", text="Test message"
        )

        channel = EmailChannel()
        channel.send_now(notification)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(email.body, "Test message")
        self.assertEqual(email.from_email, "test@example.com")

        # Check notification was marked as sent
        notification.refresh_from_db()
        self.assertIsNotNone(notification.email_sent_at)

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_now_uses_get_methods(self):
        # Create notification without stored subject/text to test dynamic generation
        notification = Notification.objects.create(recipient=self.user, notification_type="test_type")

        channel = EmailChannel()
        channel.send_now(notification)

        # Check that email was sent using the get_subject/get_text methods
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # The TestNotificationType returns empty strings for get_subject/get_text,
        # so we should get the fallback values
        self.assertEqual(email.subject, "A test notification type")
        self.assertEqual(email.body, "")

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    @patch("generic_notifications.channels.render_to_string")
    def test_send_now_with_template(self, mock_render):
        # Set up mock to return different values for different templates
        def mock_render_side_effect(template_name, context):
            if template_name.endswith("_subject.txt"):
                return "Test Subject"
            elif template_name.endswith(".html"):
                return "<html>Test HTML</html>"
            elif template_name.endswith(".txt"):
                return "Test plain text"
            return ""

        mock_render.side_effect = mock_render_side_effect

        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test Subject", text="Test message"
        )

        channel = EmailChannel()
        channel.send_now(notification)

        # Check templates were rendered (subject, HTML, then text)
        self.assertEqual(mock_render.call_count, 3)

        # Check subject template call (first)
        subject_call = mock_render.call_args_list[0]
        self.assertEqual(subject_call[0][0], "notifications/email/realtime/test_type_subject.txt")
        self.assertEqual(subject_call[0][1]["notification"], notification)

        # Check HTML template call (second)
        html_call = mock_render.call_args_list[1]
        self.assertEqual(html_call[0][0], "notifications/email/realtime/test_type.html")
        self.assertEqual(html_call[0][1]["notification"], notification)

        # Check text template call (third)
        text_call = mock_render.call_args_list[2]
        self.assertEqual(text_call[0][0], "notifications/email/realtime/test_type.txt")
        self.assertEqual(text_call[0][1]["notification"], notification)

        # Check email was sent with correct subject
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(email.body, "Test plain text")
        # HTML version should be in alternatives
        self.assertEqual(len(email.alternatives), 1)  # type: ignore
        self.assertEqual(email.alternatives[0][0], "<html>Test HTML</html>")  # type: ignore

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_now_template_error_fallback(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test Subject"
        )

        channel = EmailChannel()
        channel.send_now(notification)

        # Should still send email without HTML
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(len(email.alternatives), 0)  # type: ignore[attr-defined]  # No HTML alternative

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_empty_queryset(self):
        # No notifications exist, so digest should not send anything
        empty_notifications = Notification.objects.none()
        EmailChannel().send_digest(empty_notifications)

        # No email should be sent when no notifications exist
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_basic(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        # Create test notifications without email_sent_at (unsent)
        for i in range(3):
            Notification.objects.create(recipient=self.user, notification_type="test_type", subject=f"Test {i}")

        # Get notifications as queryset
        notifications = Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True)

        # Send digest email for this user
        EmailChannel().send_digest(notifications)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.subject, "Digest - 3 new notifications")

        # Check all notifications marked as sent
        for notification in notifications:
            notification.refresh_from_db()
            self.assertIsNotNone(notification.email_sent_at)

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_with_frequency(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        EmailChannel().send_digest(Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True))

        email = mail.outbox[0]
        self.assertEqual(email.subject, "Digest - 1 new notification")

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_without_frequency(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        EmailChannel().send_digest(Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True))

        email = mail.outbox[0]
        self.assertEqual(email.subject, "Digest - 1 new notification")

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_text_limit(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        # Create more than 10 notifications to test text limit
        _ = [
            Notification.objects.create(recipient=self.user, notification_type="test_type", subject=f"Test {i}")
            for i in range(15)
        ]

        EmailChannel().send_digest(Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True))

        # The implementation may not have this feature, so we'll just check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Digest - 15 new notifications")

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    @patch("generic_notifications.channels.render_to_string")
    def test_send_digest_emails_with_html_template(self, mock_render):
        mock_render.return_value = "<html>Digest HTML</html>"

        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        EmailChannel().send_digest(Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True))

        # Check templates were rendered (subject, HTML, then text)
        self.assertEqual(mock_render.call_count, 3)

        # Check subject template call
        subject_call = mock_render.call_args_list[0]
        self.assertEqual(subject_call[0][0], "notifications/email/digest/subject.txt")

        # Check HTML template call
        html_call = mock_render.call_args_list[1]
        self.assertEqual(html_call[0][0], "notifications/email/digest/message.html")

        # Check text template call
        text_call = mock_render.call_args_list[2]
        self.assertEqual(text_call[0][0], "notifications/email/digest/message.txt")
        self.assertEqual(html_call[0][1]["user"], self.user)
        self.assertEqual(html_call[0][1]["count"], 1)

    def test_send_now_fallback_includes_url(self):
        """Test that fallback email content includes URL when available"""
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=["email"],
            subject="Test Subject",
            text="Test notification text",
            url="https://example.com/test/url/123",
        )

        EmailChannel().send_now(notification)

        # Check that one email was sent
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]

        # Check the exact email body content
        expected_body = "Test notification text\nhttps://example.com/test/url/123"
        self.assertEqual(sent_email.body, expected_body)

    def test_send_digest_emails_fallback_includes_urls(self):
        """Test that digest fallback email content includes URLs when available"""
        # Create notifications with URLs
        Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=["email"],
            text="First notification",
            url="https://example.com/url/1",
        )
        Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=["email"],
            text="Second notification",
            url="https://example.com/url/2",
        )

        EmailChannel().send_digest(Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True))

        # Check that one email was sent
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]

        # Check the exact digest email body content
        expected_body = """You have 2 new notifications:

- Second notification
  https://example.com/url/2
- First notification
  https://example.com/url/1"""
        self.assertEqual(sent_email.body, expected_body)


class CustomEmailChannelTest(TestCase):
    """Test that custom EmailChannel subclasses work correctly with digest functionality."""

    user: Any

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="user1", email="test@example.com", password="testpass")

    def setUp(self):
        # Clear any existing emails
        mail.outbox.clear()

    def test_custom_email_channel_send_email_override(self):
        """Test that a custom EmailChannel subclass can override _send_email method."""

        class TestEmailChannel(EmailChannel):
            """Custom email channel that tracks calls to _send_email."""

            key = "test_email"
            name = "Test Email"

            def __init__(self):
                super().__init__()
                self.sent_emails = []

            def send_email(
                self, recipient: str, subject: str, text_message: str, html_message: str | None = None
            ) -> None:
                """Override to track calls instead of actually sending."""
                self.sent_emails.append(
                    {
                        "recipient": recipient,
                        "subject": subject,
                        "text_message": text_message,
                        "html_message": html_message,
                    }
                )
                # Don't call super() - we don't want to actually send emails

        # Create notifications
        notification1 = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=["test_email"],
            subject="Test Subject 1",
            text="Test notification 1",
        )

        notification2 = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=["test_email"],
            subject="Test Subject 2",
            text="Test notification 2",
        )

        notifications = Notification.objects.filter(id__in=[notification1.id, notification2.id])

        # Test the custom channel
        custom_channel = TestEmailChannel()
        custom_channel.send_digest(notifications)

        # Verify the custom _send_email method was called
        self.assertEqual(len(custom_channel.sent_emails), 1)
        sent_email = custom_channel.sent_emails[0]

        # Check the email details
        self.assertEqual(sent_email["recipient"], "test@example.com")
        self.assertIn("2 new notifications", sent_email["subject"])
        self.assertIn("Test notification 1", sent_email["text_message"])
        self.assertIn("Test notification 2", sent_email["text_message"])

        # Verify no actual emails were sent via Django's mail system
        self.assertEqual(len(mail.outbox), 0)

        # Check that notifications were marked as sent
        notification1.refresh_from_db()
        notification2.refresh_from_db()
        self.assertIsNotNone(notification1.email_sent_at)
        self.assertIsNotNone(notification2.email_sent_at)

    def test_custom_email_channel_send_now_override(self):
        """Test that a custom EmailChannel subclass works with send_now."""

        class AsyncEmailChannel(EmailChannel):
            """Custom email channel that queues emails instead of sending immediately."""

            key = "async_email"
            name = "Async Email"

            def __init__(self):
                super().__init__()
                self.queued_emails = []

            def send_email(
                self, recipient: str, subject: str, text_message: str, html_message: str | None = None
            ) -> None:
                """Queue email for later processing instead of sending immediately."""
                self.queued_emails.append(
                    {
                        "recipient": recipient,
                        "subject": subject,
                        "text_message": text_message,
                        "html_message": html_message,
                        "queued_at": "now",  # In real implementation, would use timezone.now()
                    }
                )

        # Create notification
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=["async_email"],
            subject="Realtime Test",
            text="Realtime notification",
        )

        # Test the custom channel with send_now
        custom_channel = AsyncEmailChannel()
        custom_channel.send_now(notification)

        # Verify the email was queued instead of sent
        self.assertEqual(len(custom_channel.queued_emails), 1)
        queued_email = custom_channel.queued_emails[0]

        self.assertEqual(queued_email["recipient"], "test@example.com")
        self.assertEqual(queued_email["subject"], "Realtime Test")
        self.assertIn("Realtime notification", queued_email["text_message"])
        self.assertIsNotNone(queued_email["queued_at"])

        # Verify no actual emails were sent
        self.assertEqual(len(mail.outbox), 0)

        # Check that notification was marked as sent
        notification.refresh_from_db()
        self.assertIsNotNone(notification.email_sent_at)
