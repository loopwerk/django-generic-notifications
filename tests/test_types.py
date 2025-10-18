from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase

from generic_notifications.channels import EmailChannel, WebsiteChannel
from generic_notifications.frequencies import DailyFrequency, RealtimeFrequency
from generic_notifications.models import DisabledNotificationTypeChannel, NotificationFrequency
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


class NotificationTypeTest(TestCase):
    user: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")

        # Register test notification types
        registry.register_type(TestNotificationType)

    def test_disable_channel(self):
        """Test the disable_channel class method"""
        # Verify channel is enabled initially
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Disable the channel
        TestNotificationType.disable_channel(self.user, WebsiteChannel)

        # Verify it was created
        self.assertTrue(
            DisabledNotificationTypeChannel.objects.filter(
                user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
            ).exists()
        )

        # Verify channel is now disabled
        self.assertFalse(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Disabling again should not create duplicate (get_or_create behavior)
        TestNotificationType.disable_channel(self.user, WebsiteChannel)
        self.assertEqual(
            DisabledNotificationTypeChannel.objects.filter(
                user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
            ).count(),
            1,
        )

    def test_enable_channel(self):
        """Test the enable_channel class method"""
        # First disable the channel
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
        )
        self.assertFalse(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))

        # Enable the channel
        TestNotificationType.enable_channel(self.user, WebsiteChannel)

        # Verify the disabled entry was removed
        self.assertFalse(
            DisabledNotificationTypeChannel.objects.filter(
                user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
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
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
        )

        # Website should be disabled, email should still be enabled
        self.assertFalse(TestNotificationType.is_channel_enabled(self.user, WebsiteChannel))
        self.assertTrue(TestNotificationType.is_channel_enabled(self.user, EmailChannel))

        # Different user should not be affected
        other_user = User.objects.create_user(username="other", email="other@example.com", password="pass")
        self.assertTrue(TestNotificationType.is_channel_enabled(other_user, WebsiteChannel))

    def test_get_enabled_channels(self):
        """Test the get_enabled_channels optimization method"""
        # By default, all channels should be enabled
        enabled_channels = TestNotificationType.get_enabled_channels(self.user)
        enabled_channel_keys = [ch.key for ch in enabled_channels]

        self.assertIn(WebsiteChannel.key, enabled_channel_keys)
        self.assertIn(EmailChannel.key, enabled_channel_keys)
        self.assertEqual(len(enabled_channels), 2)

        # Disable website channel
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type=TestNotificationType.key, channel=WebsiteChannel.key
        )

        # Should now only return email channel
        enabled_channels = TestNotificationType.get_enabled_channels(self.user)
        enabled_channel_keys = [ch.key for ch in enabled_channels]

        self.assertNotIn(WebsiteChannel.key, enabled_channel_keys)
        self.assertIn(EmailChannel.key, enabled_channel_keys)
        self.assertEqual(len(enabled_channels), 1)

        # Different user should not be affected
        other_user = User.objects.create_user(username="other2", email="other2@example.com", password="pass")
        other_enabled_channels = TestNotificationType.get_enabled_channels(other_user)
        other_enabled_channel_keys = [ch.key for ch in other_enabled_channels]

        self.assertIn(WebsiteChannel.key, other_enabled_channel_keys)
        self.assertIn(EmailChannel.key, other_enabled_channel_keys)
        self.assertEqual(len(other_enabled_channels), 2)

    def test_set_frequency(self):
        # Set frequency for the first time
        TestNotificationType.set_frequency(self.user, DailyFrequency)

        # Verify it was created
        freq = NotificationFrequency.objects.get(user=self.user, notification_type=TestNotificationType.key)
        self.assertEqual(freq.frequency, DailyFrequency.key)

        # Update to a different frequency
        registry.register_frequency(RealtimeFrequency, force=True)
        TestNotificationType.set_frequency(self.user, RealtimeFrequency)

        # Verify it was updated
        freq.refresh_from_db()
        self.assertEqual(freq.frequency, RealtimeFrequency.key)

        # Verify there's still only one record
        self.assertEqual(
            NotificationFrequency.objects.filter(user=self.user, notification_type=TestNotificationType.key).count(), 1
        )

    def test_get_frequency_with_user_preference(self):
        # Set user preference
        NotificationFrequency.objects.create(
            user=self.user, notification_type=TestNotificationType.key, frequency=DailyFrequency.key
        )

        # Get frequency should return the user's preference
        frequency_cls = TestNotificationType.get_frequency(self.user)
        self.assertEqual(frequency_cls.key, DailyFrequency.key)
        self.assertEqual(frequency_cls, DailyFrequency)

    def test_get_frequency_returns_default_when_no_preference(self):
        # TestNotificationType has default_frequency = DailyFrequency
        frequency_cls = TestNotificationType.get_frequency(self.user)
        self.assertEqual(frequency_cls.key, DailyFrequency.key)
        self.assertEqual(frequency_cls, DailyFrequency)

    def test_get_frequency_with_custom_default(self):
        # Create a notification type with a different default
        registry.register_frequency(RealtimeFrequency, force=True)

        class RealtimeNotificationType(NotificationType):
            key = "realtime_type"
            name = "Realtime Type"
            default_frequency = RealtimeFrequency

        registry.register_type(RealtimeNotificationType)

        # Should return the custom default
        frequency_cls = RealtimeNotificationType.get_frequency(self.user)
        self.assertEqual(frequency_cls.key, RealtimeFrequency.key)
        self.assertEqual(frequency_cls, RealtimeFrequency)

    def test_reset_to_default(self):
        # First set a custom preference
        NotificationFrequency.objects.create(
            user=self.user, notification_type=TestNotificationType.key, frequency=DailyFrequency.key
        )
        self.assertTrue(
            NotificationFrequency.objects.filter(user=self.user, notification_type=TestNotificationType.key).exists()
        )

        # Reset to default
        TestNotificationType.reset_frequency_to_default(self.user)

        # Verify the custom preference was removed
        self.assertFalse(
            NotificationFrequency.objects.filter(user=self.user, notification_type=TestNotificationType.key).exists()
        )

        # Getting frequency should now return the default
        frequency_cls = TestNotificationType.get_frequency(self.user)
        self.assertEqual(frequency_cls, TestNotificationType.default_frequency)


class ForbiddenChannelsNotificationType(NotificationType):
    key = "forbidden_test_type"
    name = "Forbidden Test Type"
    description = "A test notification type with forbidden channels"
    forbidden_channels = [WebsiteChannel]


class TestForbiddenChannels(TestCase):
    user: Any

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username="forbidden_test", email="forbidden@example.com", password="testpass"
        )
        registry.register_type(ForbiddenChannelsNotificationType)

    def test_forbidden_channels_not_in_enabled_channels(self):
        """Test that forbidden channels are not included in get_enabled_channels"""
        enabled_channels = ForbiddenChannelsNotificationType.get_enabled_channels(self.user)
        enabled_channel_keys = [ch.key for ch in enabled_channels]

        # Website channel should not be in enabled channels
        self.assertNotIn(WebsiteChannel.key, enabled_channel_keys)
        # Email channel should still be enabled
        self.assertIn(EmailChannel.key, enabled_channel_keys)

    def test_forbidden_channels_filtered_even_when_explicitly_enabled(self):
        """Test that forbidden channels are filtered out even if user tries to enable them"""
        # Try to enable the forbidden channel (this should have no effect)
        ForbiddenChannelsNotificationType.enable_channel(self.user, WebsiteChannel)

        enabled_channels = ForbiddenChannelsNotificationType.get_enabled_channels(self.user)
        enabled_channel_keys = [ch.key for ch in enabled_channels]

        # Website channel should still not be in enabled channels
        self.assertNotIn(WebsiteChannel.key, enabled_channel_keys)

    def test_forbidden_channels_filtered_when_not_disabled(self):
        """Test that forbidden channels are filtered out regardless of disabled state"""
        # Ensure no disabled entry exists for the forbidden channel
        DisabledNotificationTypeChannel.objects.filter(
            user=self.user, notification_type=ForbiddenChannelsNotificationType.key, channel=WebsiteChannel.key
        ).delete()

        enabled_channels = ForbiddenChannelsNotificationType.get_enabled_channels(self.user)
        enabled_channel_keys = [ch.key for ch in enabled_channels]

        # Website channel should still not be in enabled channels
        self.assertNotIn(WebsiteChannel.key, enabled_channel_keys)
