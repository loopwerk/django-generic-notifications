from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.template import TemplateDoesNotExist
from django.test import TestCase, override_settings

from generic_notifications.channels import BaseChannel, EmailChannel, WebsiteChannel
from generic_notifications.frequencies import DailyFrequency, RealtimeFrequency
from generic_notifications.models import (
    Notification,
    NotificationFrequencyPreference,
    NotificationTypeChannelPreference,
)
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

from .test_helpers import create_notification_with_channels

User = get_user_model()


# Test subclasses for abstract base classes
class TestNotificationType(NotificationType):
    key = "test_type"
    name = "Test Type"
    description = "A test notification type"
    default_frequency = RealtimeFrequency


class NotificationChannelTest(TestCase):
    user: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="user1", email="test@example.com", password="testpass")

    def test_notification_channel_is_abstract(self):
        class TestChannel(BaseChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        channel = TestChannel()
        self.assertEqual(channel.key, "test")
        self.assertEqual(channel.name, "Test")

    def test_channel_preferences_work_correctly(self):
        """Test that channel preferences correctly enable/disable channels per notification type."""
        # Disable website channel for test_type notifications
        NotificationTypeChannelPreference.objects.create(
            user=self.user,
            notification_type="test_type",
            channel="website",
            enabled=False,
        )

        # Should be disabled for test_type
        enabled_channels = TestNotificationType.get_enabled_channels(self.user)
        self.assertNotIn(WebsiteChannel, enabled_channels)

        # But should still include email channel
        self.assertIn(EmailChannel, enabled_channels)

    def test_digest_only_channel_never_sends_immediately(self):
        """Test that channels with supports_realtime=False never send immediately."""

        class DigestOnlyChannel(BaseChannel):
            key = "digest_only"
            name = "Digest Only"
            supports_realtime = False
            supports_digest = True

            def send_now(self, notification):
                raise AssertionError("send_now should never be called for digest-only channel")

        channel = DigestOnlyChannel()
        notification = Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        # Process should not call send_now (would raise AssertionError if it did)
        channel.process(notification)


class WebsiteChannelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user2", email="test@example.com", password="testpass")
        registry.register_type(TestNotificationType)

        self.notification = Notification.objects.create(
            recipient=self.user,
            notification_type="test_type",
            subject="Test Subject",
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
        notification = create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
        )

        channel = EmailChannel()
        channel.process(notification)

        # Should send email immediately for realtime frequency
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])

        # Check notification was marked as sent
        notification.refresh_from_db()
        self.assertTrue(notification.is_sent_on_channel(EmailChannel))

    def test_process_digest_frequency(self):
        # Set user preference to daily (non-realtime)
        NotificationFrequencyPreference.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        notification = create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
        )

        channel = EmailChannel()
        channel.process(notification)

        # Should not send email immediately for digest frequency
        self.assertEqual(len(mail.outbox), 0)

        # Notification should not be marked as sent
        notification.refresh_from_db()
        self.assertFalse(notification.is_sent_on_channel(EmailChannel))

    def test_should_send_with_email(self):
        """Test that should_send returns True when user has email"""
        notification = create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
        )

        self.assertTrue(EmailChannel.should_send(notification))

    def test_should_send_without_email(self):
        """Test that should_send returns False when user has no email"""
        # Create user without email
        user_no_email = User.objects.create_user(username="user2", password="testpass")
        user_no_email.email = ""
        user_no_email.save()

        notification = create_notification_with_channels(
            user=user_no_email,
            notification_type="test_type",
        )

        self.assertFalse(EmailChannel.should_send(notification))

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_now_basic(self):
        notification = create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
            subject="Test Subject",
            text="Test message",
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
        self.assertTrue(notification.is_sent_on_channel(EmailChannel))

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_now_uses_get_methods(self):
        # Create notification without stored subject/text to test dynamic generation
        notification = create_notification_with_channels(user=self.user, notification_type="test_type")

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
    @patch("generic_notifications.channels.select_template")
    def test_send_now_with_template(self, mock_select):
        # Create mock template objects that return the expected content
        class MockTemplate:
            def __init__(self, content):
                self.content = content

            def render(self, context):
                return self.content

        # Set up mock to return different templates based on the template list
        def mock_select_side_effect(template_list):
            # Check the first template in the list to determine what to return
            first_template = template_list[0]
            if first_template.endswith("_subject.txt"):
                return MockTemplate("Test Subject")
            elif first_template.endswith(".html"):
                return MockTemplate("<html>Test HTML</html>")
            elif first_template.endswith(".txt"):
                return MockTemplate("Test plain text")
            return MockTemplate("")

        mock_select.side_effect = mock_select_side_effect

        notification = create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
            subject="Test Subject",
            text="Test message",
        )

        channel = EmailChannel()
        channel.send_now(notification)

        # Check email was sent with correct subject and text
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(email.body, "Test plain text")
        # HTML version should be in alternatives
        self.assertEqual(len(email.alternatives), 1)  # type: ignore
        self.assertEqual(email.alternatives[0][0], "<html>Test HTML</html>")  # type: ignore

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    @patch("generic_notifications.channels.select_template")
    def test_send_now_with_fallback_templates(self, mock_select):
        """Test that fallback templates are used when notification-specific templates don't exist."""

        # Create mock template objects
        class MockTemplate:
            def __init__(self, content):
                self.content = content

            def render(self, context):
                return self.content

        # Set up mock to simulate using fallback templates (second in the list)
        def mock_select_side_effect(template_list):
            if "subject.txt" in template_list[1]:
                return MockTemplate("Fallback Subject")
            elif "body.html" in template_list[1]:
                return MockTemplate("<html>Fallback HTML Body</html>")
            elif "body.txt" in template_list[1]:
                return MockTemplate("Fallback Text Body")
            raise TemplateDoesNotExist("No templates found")

        mock_select.side_effect = mock_select_side_effect

        notification = create_notification_with_channels(
            user=self.user,
            notification_type="new_type",
            subject="Original Subject",
            text="Original message",
        )

        channel = EmailChannel()
        channel.send_now(notification)

        # Check email was sent with fallback content
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Fallback Subject")
        self.assertEqual(email.body, "Fallback Text Body")
        # HTML version should be in alternatives
        self.assertEqual(len(email.alternatives), 1)
        self.assertEqual(email.alternatives[0][0], "<html>Fallback HTML Body</html>")

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_now_template_error_fallback(self):
        notification = create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
            subject="Test Subject",
        )

        channel = EmailChannel()
        channel.send_now(notification)

        # Should still send email without HTML
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(len(email.alternatives), 0)  # type: ignore[attr-defined]  # No HTML alternative

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_basic(self):
        # Set user to daily frequency to prevent realtime sending
        NotificationFrequencyPreference.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        # Create test notifications without email_sent_at (unsent)
        for i in range(3):
            create_notification_with_channels(
                user=self.user,
                notification_type="test_type",
                subject=f"Test {i}",
            )

        # Get notifications as queryset
        notifications = Notification.objects.filter(
            recipient=self.user,
            channels__channel="email",
            channels__sent_at__isnull=True,
        )

        # Send digest email for this user
        EmailChannel().send_digest(notifications, DailyFrequency)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.subject, "Daily digest - 3 new notifications")

        # Check all notifications marked as sent
        for notification in notifications:
            notification.refresh_from_db()
            self.assertTrue(notification.is_sent_on_channel(EmailChannel))

    @override_settings(DEFAULT_FROM_EMAIL="test@example.com")
    def test_send_digest_emails_with_frequency(self):
        # Set user to daily frequency to prevent realtime sending
        NotificationFrequencyPreference.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        create_notification_with_channels(
            user=self.user,
            notification_type="test_type",
            subject="Test",
        )

        EmailChannel().send_digest(
            Notification.objects.filter(
                recipient=self.user,
                channels__channel="email",
                channels__sent_at__isnull=True,
            ),
            DailyFrequency,
        )

        email = mail.outbox[0]
        self.assertEqual(email.subject, "Daily digest - 1 new notification")

    def test_send_now_fallback_includes_url(self):
        """Test that fallback email content includes URL when available"""
        notification = create_notification_with_channels(
            user=self.user,
            notification_type=TestNotificationType.key,
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
        create_notification_with_channels(
            user=self.user,
            notification_type=TestNotificationType.key,
            text="First notification",
            url="https://example.com/url/1",
        )
        create_notification_with_channels(
            user=self.user,
            notification_type=TestNotificationType.key,
            text="Second notification",
            url="https://example.com/url/2",
        )

        EmailChannel().send_digest(
            Notification.objects.filter(
                recipient=self.user,
                channels__channel="email",
                channels__sent_at__isnull=True,
            ),
            DailyFrequency,
        )

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
        notification1 = create_notification_with_channels(
            user=self.user,
            channels=["test_email"],
            notification_type=TestNotificationType.key,
            subject="Test Subject 1",
            text="Test notification 1",
        )

        notification2 = create_notification_with_channels(
            user=self.user,
            channels=["test_email"],
            notification_type=TestNotificationType.key,
            subject="Test Subject 2",
            text="Test notification 2",
        )

        notifications = Notification.objects.filter(id__in=[notification1.id, notification2.id])

        # Test the custom channel
        custom_channel = TestEmailChannel()
        custom_channel.send_digest(notifications, DailyFrequency)

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
        self.assertTrue(notification1.is_sent_on_channel(TestEmailChannel))
        self.assertTrue(notification2.is_sent_on_channel(TestEmailChannel))

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
        notification = create_notification_with_channels(
            user=self.user,
            channels=["async_email"],
            notification_type=TestNotificationType.key,
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
        self.assertTrue(notification.is_sent_on_channel(AsyncEmailChannel))
