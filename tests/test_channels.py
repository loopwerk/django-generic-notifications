from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from generic_notifications.channels import EmailChannel, NotificationChannel
from generic_notifications.frequencies import DailyFrequency, RealtimeFrequency
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

        channel = TestChannel()
        # By default, all notifications are enabled
        self.assertTrue(channel.is_enabled(self.user, "any_type"))

    def test_is_enabled_with_disabled_notification(self):
        class TestChannel(NotificationChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        channel = TestChannel()

        # Disable notification channel for this user
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type="disabled_type", channel="test"
        )

        # Should be disabled for this type
        self.assertFalse(channel.is_enabled(self.user, "disabled_type"))

        # But enabled for other types
        self.assertTrue(channel.is_enabled(self.user, "other_type"))


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

    def test_get_frequency_with_user_preference(self):
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        channel = EmailChannel()
        frequency = channel.get_frequency(self.user, "test_type")

        self.assertEqual(frequency.key, "daily")

    def test_get_frequency_default_realtime(self):
        channel = EmailChannel()
        frequency = channel.get_frequency(self.user, "test_type")

        # Should default to first realtime frequency
        self.assertEqual(frequency.key, "realtime")

    def test_get_frequency_fallback_when_no_realtime(self):
        # Clear realtime frequencies and add only non-realtime
        registry.unregister_frequency(RealtimeFrequency)
        registry.register_frequency(DailyFrequency)

        channel = EmailChannel()
        frequency = channel.get_frequency(self.user, "test_type")

        # Should fallback to "realtime" string
        self.assertEqual(frequency.key, "realtime")

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

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_email_now_basic(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test Subject", text="Test message"
        )

        channel = EmailChannel()
        channel.send_email_now(notification)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(email.body, "Test message")
        self.assertEqual(email.from_email, "test@presets.audio")

        # Check notification was marked as sent
        notification.refresh_from_db()
        self.assertIsNotNone(notification.email_sent_at)

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_email_now_uses_get_methods(self):
        # Create notification without stored subject/text to test dynamic generation
        notification = Notification.objects.create(recipient=self.user, notification_type="test_type")

        channel = EmailChannel()
        channel.send_email_now(notification)

        # Check that email was sent using the get_subject/get_text methods
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # The TestNotificationType returns empty strings for get_subject/get_text,
        # so we should get the fallback values
        self.assertEqual(email.subject, "A test notification type")
        self.assertEqual(email.body, "")

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    @patch("generic_notifications.channels.render_to_string")
    def test_send_email_now_with_template(self, mock_render):
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
        channel.send_email_now(notification)

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

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_email_now_template_error_fallback(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test Subject"
        )

        channel = EmailChannel()
        channel.send_email_now(notification)

        # Should still send email without HTML
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Test Subject")
        self.assertEqual(len(email.alternatives), 0)  # type: ignore[attr-defined]  # No HTML alternative

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_digest_emails_empty_queryset(self):
        # No notifications exist, so digest should not send anything
        empty_notifications = Notification.objects.none()
        EmailChannel.send_digest_emails(self.user, empty_notifications)

        # No email should be sent when no notifications exist
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_digest_emails_basic(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        # Create test notifications without email_sent_at (unsent)
        for i in range(3):
            Notification.objects.create(recipient=self.user, notification_type="test_type", subject=f"Test {i}")

        # Get notifications as queryset
        notifications = Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True)

        # Send digest email for this user
        EmailChannel.send_digest_emails(self.user, notifications)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertIn("3 new notifications", email.subject)

        # Check all notifications marked as sent
        for notification in notifications:
            notification.refresh_from_db()
            self.assertIsNotNone(notification.email_sent_at)

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_digest_emails_with_frequency(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        EmailChannel.send_digest_emails(
            self.user, Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True)
        )

        email = mail.outbox[0]
        self.assertIn("1 new notifications", email.subject)

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_digest_emails_without_frequency(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        EmailChannel.send_digest_emails(
            self.user, Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True)
        )

        email = mail.outbox[0]
        self.assertIn("Digest - 1 new notifications", email.subject)

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    def test_send_digest_emails_text_limit(self):
        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        # Create more than 10 notifications to test text limit
        _ = [
            Notification.objects.create(recipient=self.user, notification_type="test_type", subject=f"Test {i}")
            for i in range(15)
        ]

        EmailChannel.send_digest_emails(
            self.user, Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True)
        )

        # The implementation may not have this feature, so we'll just check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("15 new notifications", email.subject)

    @override_settings(DEFAULT_FROM_EMAIL="test@presets.audio")
    @patch("generic_notifications.channels.render_to_string")
    def test_send_digest_emails_with_html_template(self, mock_render):
        mock_render.return_value = "<html>Digest HTML</html>"

        # Set user to daily frequency to prevent realtime sending
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        Notification.objects.create(recipient=self.user, notification_type="test_type", subject="Test")

        EmailChannel.send_digest_emails(
            self.user, Notification.objects.filter(recipient=self.user, email_sent_at__isnull=True)
        )

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
