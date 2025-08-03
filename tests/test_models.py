from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from generic_notifications.channels import EmailChannel, WebsiteChannel
from generic_notifications.frequencies import DailyFrequency, RealtimeFrequency
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency, Notification
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

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
            user=self.user, notification_type="test_type", channel="website"
        )

        self.assertEqual(disabled.user, self.user)
        self.assertEqual(disabled.notification_type, "test_type")
        self.assertEqual(disabled.channel, "website")

    def test_clean_with_invalid_notification_type(self):
        disabled = DisabledNotificationTypeChannel(user=self.user, notification_type="invalid_type", channel="website")

        with self.assertRaises(ValidationError) as cm:
            disabled.clean()

        self.assertIn("Unknown notification type: invalid_type", str(cm.exception))

    def test_clean_with_invalid_channel(self):
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type="test_type", channel="invalid_channel"
        )

        with self.assertRaises(ValidationError) as cm:
            disabled.clean()

        self.assertIn("Unknown channel: invalid_channel", str(cm.exception))

    def test_clean_with_valid_data(self):
        disabled = DisabledNotificationTypeChannel(user=self.user, notification_type="test_type", channel="website")

        # Should not raise any exception
        disabled.clean()

    def test_clean_prevents_disabling_required_channel(self):
        """Test that users cannot disable required channels for notification types"""
        disabled = DisabledNotificationTypeChannel(user=self.user, notification_type="system_message", channel="email")

        with self.assertRaises(ValidationError) as cm:
            disabled.clean()

        self.assertIn("Cannot disable email channel for System Message - this channel is required", str(cm.exception))

    def test_clean_allows_disabling_non_required_channel(self):
        """Test that users can disable non-required channels for notification types with required channels"""
        disabled = DisabledNotificationTypeChannel(
            user=self.user, notification_type="system_message", channel="website"
        )

        # Should not raise any exception - website is not required for system_message
        disabled.clean()

    def test_disable_channel(self):
        """Test the disable_channel class method"""
        # Verify channel is enabled initially
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Disable the channel
        TestNotificationType.disable_channel(self.user, WebsiteChannel)

        # Verify it was created
        self.assertTrue(
            DisabledNotificationTypeChannel.objects.filter(
                user=self.user, notification_type="test_type", channel="website"
            ).exists()
        )

        # Verify channel is now disabled
        self.assertFalse(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Disabling again should not create duplicate (get_or_create behavior)
        TestNotificationType.disable_channel(self.user, WebsiteChannel)
        self.assertEqual(
            DisabledNotificationTypeChannel.objects.filter(
                user=self.user, notification_type="test_type", channel="website"
            ).count(),
            1,
        )

    def test_enable_channel(self):
        """Test the enable_channel class method"""
        # First disable the channel
        DisabledNotificationTypeChannel.objects.create(user=self.user, notification_type="test_type", channel="website")
        self.assertFalse(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Enable the channel
        TestNotificationType.enable_channel(self.user, WebsiteChannel)

        # Verify the disabled entry was removed
        self.assertFalse(
            DisabledNotificationTypeChannel.objects.filter(
                user=self.user, notification_type="test_type", channel="website"
            ).exists()
        )

        # Verify channel is now enabled
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Enabling an already enabled channel should work without error
        TestNotificationType.enable_channel(self.user, WebsiteChannel)
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

    def test_is_channel_enabled(self):
        """Test the is_channel_enabled class method"""
        # By default, all channels should be enabled
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, EmailChannel))

        # Disable website channel
        DisabledNotificationTypeChannel.objects.create(user=self.user, notification_type="test_type", channel="website")

        # Website should be disabled, email should still be enabled
        self.assertFalse(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, EmailChannel))

        # Different user should not be affected
        other_user = User.objects.create_user(username="other", email="other@example.com", password="pass")
        self.assertTrue(TestNotificationType.is_channel_enabled(other_user, WebsiteChannel))


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
        frequency = EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        self.assertEqual(frequency.user, self.user)
        self.assertEqual(frequency.notification_type, "test_type")
        self.assertEqual(frequency.frequency, "daily")

    def test_unique_together_constraint(self):
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        with self.assertRaises(IntegrityError):
            EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

    def test_clean_with_invalid_notification_type(self):
        frequency = EmailFrequency(user=self.user, notification_type="invalid_type", frequency="daily")

        with self.assertRaises(ValidationError) as cm:
            frequency.clean()

        self.assertIn("Unknown notification type: invalid_type", str(cm.exception))

    def test_clean_with_invalid_frequency(self):
        frequency = EmailFrequency(user=self.user, notification_type="test_type", frequency="invalid_frequency")

        with self.assertRaises(ValidationError) as cm:
            frequency.clean()

        self.assertIn("Unknown frequency: invalid_frequency", str(cm.exception))

    def test_clean_with_valid_data(self):
        frequency = EmailFrequency(user=self.user, notification_type="test_type", frequency="daily")

        # Should not raise any exception
        frequency.clean()

    def test_set_frequency(self):
        # Set frequency for the first time
        TestNotificationType.set_email_frequency(self.user, DailyFrequency)

        # Verify it was created
        freq = EmailFrequency.objects.get(user=self.user, notification_type="test_type")
        self.assertEqual(freq.frequency, "daily")

        # Update to a different frequency
        registry.register_frequency(RealtimeFrequency, force=True)
        TestNotificationType.set_email_frequency(self.user, RealtimeFrequency)

        # Verify it was updated
        freq.refresh_from_db()
        self.assertEqual(freq.frequency, "realtime")

        # Verify there's still only one record
        self.assertEqual(EmailFrequency.objects.filter(user=self.user, notification_type="test_type").count(), 1)

    def test_get_frequency_with_user_preference(self):
        # Set user preference
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")

        # Get frequency should return the user's preference
        frequency_cls = TestNotificationType.get_email_frequency(self.user)
        self.assertEqual(frequency_cls.key, "daily")
        self.assertEqual(frequency_cls, DailyFrequency)

    def test_get_frequency_returns_default_when_no_preference(self):
        # TestNotificationType has default_email_frequency = DailyFrequency
        frequency_cls = TestNotificationType.get_email_frequency(self.user)
        self.assertEqual(frequency_cls.key, "daily")
        self.assertEqual(frequency_cls, DailyFrequency)

    def test_get_frequency_with_custom_default(self):
        # Create a notification type with a different default
        registry.register_frequency(RealtimeFrequency, force=True)

        class RealtimeNotificationType(NotificationType):
            key = "realtime_type"
            name = "Realtime Type"
            default_email_frequency = RealtimeFrequency

        registry.register_type(RealtimeNotificationType)

        # Should return the custom default
        frequency_cls = RealtimeNotificationType.get_email_frequency(self.user)
        self.assertEqual(frequency_cls.key, "realtime")
        self.assertEqual(frequency_cls, RealtimeFrequency)

    def test_reset_to_default(self):
        # First set a custom preference
        EmailFrequency.objects.create(user=self.user, notification_type="test_type", frequency="daily")
        self.assertTrue(EmailFrequency.objects.filter(user=self.user, notification_type="test_type").exists())

        # Reset to default
        TestNotificationType.reset_email_frequency_to_default(self.user)

        # Verify the custom preference was removed
        self.assertFalse(EmailFrequency.objects.filter(user=self.user, notification_type="test_type").exists())

        # Getting frequency should now return the default
        frequency_cls = TestNotificationType.get_email_frequency(self.user)
        self.assertEqual(frequency_cls, TestNotificationType.default_email_frequency)


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
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
        )

        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.notification_type, "test_type")
        self.assertIsNotNone(notification.added)
        self.assertIsNone(notification.read)
        self.assertEqual(notification.metadata, {})

    def test_create_full_notification(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type="test_type",
            subject="Test Subject",
            text="Test notification text",
            url="/test/url",
            actor=self.actor,
            metadata={"key": "value"},
        )

        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.notification_type, "test_type")
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
            recipient=self.user, notification_type="test_type", content_type=content_type, object_id=target_user.id
        )

        self.assertEqual(notification.target, target_user)

    def test_clean_with_invalid_notification_type(self):
        notification = Notification(recipient=self.user, notification_type="invalid_type")

        with self.assertRaises(ValidationError) as cm:
            notification.clean()

        self.assertIn("Unknown notification type: invalid_type", str(cm.exception))

    def test_clean_with_valid_notification_type(self):
        notification = Notification(recipient=self.user, notification_type="test_type")

        # Should not raise any exception
        notification.clean()

    def test_mark_as_read(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
        )

        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read)

        notification.mark_as_read()
        notification.refresh_from_db()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read)

    def test_mark_as_read_idempotent(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
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
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
        )

        self.assertFalse(notification.is_read)

        notification.read = timezone.now()
        self.assertTrue(notification.is_read)

    def test_email_sent_tracking(self):
        notification = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website", "email"]
        )

        self.assertIsNone(notification.email_sent_at)

        # Simulate email being sent
        sent_time = timezone.now()
        notification.email_sent_at = sent_time
        notification.save()

        notification.refresh_from_db()
        self.assertEqual(notification.email_sent_at, sent_time)
