from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from generic_notifications.channels import EmailChannel, WebsiteChannel
from generic_notifications.frequencies import DailyFrequency
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency, Notification
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType, SystemMessage

User = get_user_model()


# Test subclasses for the ABC base classes
class TestNotificationType(NotificationType):
    key = "test_type"
    name = "Test Type"
    description = "A test notification type"

    def get_subject(self, notification):
        return "Test Subject"

    def get_text(self, notification):
        return "Test notification text"


class TestChannel:
    """Test channel for validation - simplified version"""

    key = "website"
    name = "Website"


class DisabledNotificationTypeChannelModelTest(TestCase):
    user: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")

        # Register test notification types and import channels for validation
        registry.register_type(TestNotificationType)

    def test_create_disabled_notification(self):
        disabled = DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
        )

        self.assertEqual(disabled.user, self.user)
        self.assertEqual(disabled.notification_type, TestNotificationType.key)
        self.assertEqual(disabled.channel, WebsiteChannel.key)

    def test_clean_with_invalid_notification_type(self):
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type="invalid_type", channel=WebsiteChannel.key
        )

        with self.assertRaises(ValidationError) as cm:
            disabled.clean()

        self.assertIn("Unknown notification type: invalid_type", str(cm.exception))

    def test_clean_with_invalid_channel(self):
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type=TestNotificationType.key, channel="invalid_channel"
        )

        with self.assertRaises(ValidationError) as cm:
            disabled.clean()

        self.assertIn("Unknown channel: invalid_channel", str(cm.exception))

    def test_clean_with_valid_data(self):
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
        )

        # Should not raise any exception
        disabled.clean()

    def test_clean_prevents_disabling_required_channel(self):
        """Test that users cannot disable required channels for notification types"""
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type=SystemMessage.key, channel=EmailChannel.key
        )

        with self.assertRaises(ValidationError) as cm:
            disabled.clean()

        self.assertIn("Cannot disable email channel for System Message - this channel is required", str(cm.exception))

    def test_clean_allows_disabling_non_required_channel(self):
        """Test that users can disable non-required channels for notification types with required channels"""
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type=SystemMessage.key, channel=WebsiteChannel.key
        )

        # Should not raise any exception - website is not required for system_message
        disabled.clean()


class EmailFrequencyModelTest(TestCase):
    user: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="test2", email="test2@example.com", password="testpass")

        # Register test data
        registry.register_type(TestNotificationType)
        # Re-register DailyFrequency in case it was cleared by other tests
        registry.register_frequency(DailyFrequency, force=True)

    def test_create_email_frequency(self):
        frequency = EmailFrequency.objects.create(
            user=self.user, notification_type=TestNotificationType.key, frequency=DailyFrequency.key
        )

        self.assertEqual(frequency.user, self.user)
        self.assertEqual(frequency.notification_type, TestNotificationType.key)
        self.assertEqual(frequency.frequency, DailyFrequency.key)

    def test_unique_together_constraint(self):
        EmailFrequency.objects.create(
            user=self.user, notification_type=TestNotificationType.key, frequency=DailyFrequency.key
        )

        with self.assertRaises(IntegrityError):
            EmailFrequency.objects.create(
                user=self.user, notification_type=TestNotificationType.key, frequency=DailyFrequency.key
            )

    def test_clean_with_invalid_notification_type(self):
        frequency = EmailFrequency(user=self.user, notification_type="invalid_type", frequency=DailyFrequency.key)

        with self.assertRaises(ValidationError) as cm:
            frequency.clean()

        self.assertIn("Unknown notification type: invalid_type", str(cm.exception))

    def test_clean_with_invalid_frequency(self):
        frequency = EmailFrequency(
            user=self.user, notification_type=TestNotificationType.key, frequency="invalid_frequency"
        )

        with self.assertRaises(ValidationError) as cm:
            frequency.clean()

        self.assertIn("Unknown frequency: invalid_frequency", str(cm.exception))

    def test_clean_with_valid_data(self):
        frequency = EmailFrequency(
            user=self.user, notification_type=TestNotificationType.key, frequency=DailyFrequency.key
        )

        # Should not raise any exception
        frequency.clean()


class NotificationModelTest(TestCase):
    user: Any  # User model instance created in setUpClass
    actor: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="test3", email="test3@example.com", password="testpass")
        cls.actor = User.objects.create_user(username="actor", email="actor@example.com", password="testpass")

        # Register test notification type
        registry.register_type(TestNotificationType)

    def test_create_minimal_notification(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key, EmailChannel.key],
        )

        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.notification_type, TestNotificationType.key)
        self.assertIsNotNone(notification.added)
        self.assertIsNone(notification.read)
        self.assertEqual(notification.metadata, {})

    def test_create_full_notification(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            subject="Test Subject",
            text="Test notification text",
            url="/test/url",
            actor=self.actor,
            metadata={"key": "value"},
        )

        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.notification_type, TestNotificationType.key)
        self.assertEqual(notification.subject, "Test Subject")
        self.assertEqual(notification.text, "Test notification text")
        self.assertEqual(notification.url, "/test/url")
        self.assertEqual(notification.actor, self.actor)
        self.assertEqual(notification.metadata, {"key": "value"})

    def test_notification_with_generic_relation(self):
        # Create a user to use as target object
        target_user = User.objects.create_user(username="target", email="target@example.com", password="testpass")
        content_type = ContentType.objects.get_for_model(User)

        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            content_type=content_type,
            object_id=target_user.id,
        )

        self.assertEqual(notification.target, target_user)

    def test_clean_with_invalid_notification_type(self):
        notification = Notification(recipient=self.user, notification_type="invalid_type")

        with self.assertRaises(ValidationError) as cm:
            notification.clean()

        self.assertIn("Unknown notification type: invalid_type", str(cm.exception))

    def test_clean_with_valid_notification_type(self):
        notification = Notification(recipient=self.user, notification_type=TestNotificationType.key)

        # Should not raise any exception
        notification.clean()

    def test_mark_as_read(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key, EmailChannel.key],
        )

        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read)

        notification.mark_as_read()
        notification.refresh_from_db()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read)

    def test_mark_as_read_idempotent(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key, EmailChannel.key],
        )

        # Mark as read first time
        notification.mark_as_read()
        notification.refresh_from_db()
        first_read_time = notification.read

        # Mark as read second time
        notification.mark_as_read()
        notification.refresh_from_db()

        # Should not change the read time
        self.assertEqual(notification.read, first_read_time)

    def test_is_read_property(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key, EmailChannel.key],
        )

        self.assertFalse(notification.is_read)

        notification.read = timezone.now()
        self.assertTrue(notification.is_read)

    def test_email_sent_tracking(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key, EmailChannel.key],
        )

        self.assertIsNone(notification.email_sent_at)

        # Simulate email being sent
        sent_time = timezone.now()
        notification.email_sent_at = sent_time
        notification.save()

        notification.refresh_from_db()
        self.assertEqual(notification.email_sent_at, sent_time)

    def test_get_absolute_url_empty_url(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
        )
        self.assertEqual(notification.get_absolute_url(), "")

    def test_get_absolute_url_already_absolute(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="https://example.com/path",
        )
        self.assertEqual(notification.get_absolute_url(), "https://example.com/path")

    def test_get_absolute_url_with_setting(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="/notifications/123",
        )

        with self.settings(NOTIFICATION_BASE_URL="https://mysite.com"):
            self.assertEqual(notification.get_absolute_url(), "https://mysite.com/notifications/123")

    def test_get_absolute_url_with_setting_no_protocol_debug(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="/notifications/123",
        )

        with self.settings(NOTIFICATION_BASE_URL="mysite.com", DEBUG=True):
            # Should add http protocol in debug mode
            self.assertEqual(notification.get_absolute_url(), "http://mysite.com/notifications/123")

    def test_get_absolute_url_with_setting_no_protocol_production(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="/notifications/123",
        )

        with self.settings(NOTIFICATION_BASE_URL="mysite.com", DEBUG=False):
            # Should add https protocol in production mode
            self.assertEqual(notification.get_absolute_url(), "https://mysite.com/notifications/123")

    def test_get_absolute_url_fallback_settings(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="/notifications/123",
        )

        with self.settings(BASE_URL="https://fallback.com"):
            self.assertEqual(notification.get_absolute_url(), "https://fallback.com/notifications/123")

    def test_get_absolute_url_fallback_settings_no_protocol(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="/notifications/123",
        )

        with self.settings(BASE_URL="fallback.com", DEBUG=False):
            # Should add https protocol in production mode for fallback setting
            self.assertEqual(notification.get_absolute_url(), "https://fallback.com/notifications/123")

    def test_get_absolute_url_no_base_url(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=TestNotificationType.key,
            channels=[WebsiteChannel.key],
            url="/notifications/123",
        )

        # When no base URL is available, should return the relative URL
        self.assertEqual(notification.get_absolute_url(), "/notifications/123")
