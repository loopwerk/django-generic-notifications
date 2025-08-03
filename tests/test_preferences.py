from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase

from generic_notifications.channels import WebsiteChannel
from generic_notifications.frequencies import DailyFrequency, RealtimeFrequency
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency
from generic_notifications.preferences import get_notification_preferences, save_notification_preferences
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

User = get_user_model()


class TestNotificationType(NotificationType):
    key = "test_notification"
    name = "Test Notification"
    description = "A test notification type"
    default_email_frequency = RealtimeFrequency
    required_channels = []


class RequiredChannelNotificationType(NotificationType):
    key = "required_channel_notification"
    name = "Required Channel Notification"
    description = "A notification with required channels"
    default_email_frequency = DailyFrequency
    required_channels = [WebsiteChannel]


class GetNotificationPreferencesTest(TestCase):
    user: Any  # User model instance created in setUpClass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        # Register custom notification types
        registry.register_type(TestNotificationType, force=True)
        registry.register_type(RequiredChannelNotificationType, force=True)

    def test_opt_out_model_all_channels_enabled_by_default(self):
        """Test the opt-out model: all channels are enabled by default."""
        preferences = get_notification_preferences(self.user)

        for pref in preferences:
            if pref["notification_type"].key == "test_notification":
                self.assertTrue(pref["channels"]["website"]["enabled"])
                self.assertTrue(pref["channels"]["email"]["enabled"])
                self.assertFalse(pref["channels"]["website"]["required"])
                self.assertFalse(pref["channels"]["email"]["required"])

    def test_disabled_channels_are_reflected_in_preferences(self):
        """Test that disabled channels are properly reflected."""
        # Disable email for test notification
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type="test_notification", channel="email"
        )

        preferences = get_notification_preferences(self.user)

        for pref in preferences:
            if pref["notification_type"].key == "test_notification":
                self.assertTrue(pref["channels"]["website"]["enabled"])
                self.assertFalse(pref["channels"]["email"]["enabled"])

    def test_email_frequency_defaults_and_overrides(self):
        """Test email frequency business logic: defaults and custom overrides."""
        # First check defaults
        preferences = get_notification_preferences(self.user)

        for pref in preferences:
            if pref["notification_type"].key == "test_notification":
                self.assertEqual(pref["email_frequency"], "realtime")
            elif pref["notification_type"].key == "required_channel_notification":
                self.assertEqual(pref["email_frequency"], "daily")

        # Now override one
        EmailFrequency.objects.create(user=self.user, notification_type="test_notification", frequency="daily")

        preferences = get_notification_preferences(self.user)

        for pref in preferences:
            if pref["notification_type"].key == "test_notification":
                self.assertEqual(pref["email_frequency"], "daily")


class SaveNotificationPreferencesTest(TestCase):
    user: Any  # User model instance created in setUpClass
    other_user: Any  # Second user for isolation testing

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="testuser2", email="test2@example.com", password="testpass")
        cls.other_user = User.objects.create_user(username="otheruser", email="other@example.com", password="testpass")

        # Register custom notification types
        registry.register_type(TestNotificationType, force=True)
        registry.register_type(RequiredChannelNotificationType, force=True)

    def test_complete_form_save_workflow(self):
        """Test the complete form save workflow with channels and frequencies."""
        form_data = {
            # User wants website only for test notifications
            "test_notification__website": "on",
            "test_notification__frequency": "daily",
            # User wants both channels for required channel notifications
            "required_channel_notification__website": "on",
            "required_channel_notification__email": "on",
            "required_channel_notification__frequency": "realtime",
        }

        save_notification_preferences(self.user, form_data)

        # Verify disabled channels for our test notification type
        disabled = DisabledNotificationTypeChannel.objects.filter(user=self.user, notification_type="test_notification")
        self.assertEqual(disabled.count(), 1)
        self.assertEqual(disabled.first().channel, "email")

        # Verify frequencies (only non-defaults saved)
        frequencies = EmailFrequency.objects.filter(user=self.user).order_by("notification_type")
        self.assertEqual(frequencies.count(), 2)

        test_freq = frequencies.filter(notification_type="test_notification").first()
        self.assertEqual(test_freq.frequency, "daily")

        required_freq = frequencies.filter(notification_type="required_channel_notification").first()
        self.assertEqual(required_freq.frequency, "realtime")

    def test_preferences_cleared_before_saving_new_ones(self):
        """Test that old preferences are properly cleared when saving new ones."""
        # Create some existing preferences
        DisabledNotificationTypeChannel.objects.create(
            user=self.user, notification_type="test_notification", channel="website"
        )
        EmailFrequency.objects.create(user=self.user, notification_type="test_notification", frequency="daily")

        # Save completely different preferences
        form_data = {
            "test_notification__website": "on",
            "test_notification__email": "on",
            # No frequency specified - should use default
        }

        save_notification_preferences(self.user, form_data)

        # Old disabled entry should be gone for test_notification
        disabled = DisabledNotificationTypeChannel.objects.filter(user=self.user, notification_type="test_notification")
        self.assertEqual(disabled.count(), 0)

        # Old frequency should be gone
        frequencies = EmailFrequency.objects.filter(user=self.user)
        self.assertEqual(frequencies.count(), 0)

    def test_required_channels_ignored_in_form_data(self):
        """Test that required channels cannot be disabled even if missing from form."""
        form_data = {
            # Website not included for required_channel_notification (trying to disable it)
            "required_channel_notification__email": "on",
        }

        save_notification_preferences(self.user, form_data)

        # Website should NOT be in disabled channels because it's required
        disabled = DisabledNotificationTypeChannel.objects.filter(
            user=self.user, notification_type="required_channel_notification", channel="website"
        )
        self.assertEqual(disabled.count(), 0)

    def test_user_preferences_are_isolated(self):
        """Test that preferences are properly isolated between users."""
        # Set preferences for first user
        form_data = {"test_notification__email": "on"}
        save_notification_preferences(self.user, form_data)

        # Set different preferences for second user
        other_form_data = {"test_notification__website": "on"}
        save_notification_preferences(self.other_user, other_form_data)

        # Check first user's preferences
        user_disabled = DisabledNotificationTypeChannel.objects.filter(
            user=self.user, notification_type="test_notification"
        )
        self.assertEqual(user_disabled.count(), 1)
        self.assertEqual(user_disabled.first().channel, "website")

        # Check second user's preferences
        other_disabled = DisabledNotificationTypeChannel.objects.filter(
            user=self.other_user, notification_type="test_notification"
        )
        self.assertEqual(other_disabled.count(), 1)
        self.assertEqual(other_disabled.first().channel, "email")

    def test_only_non_default_frequencies_are_saved(self):
        """Test the optimization that only non-default frequencies are stored."""
        form_data = {
            # Using default frequency for test_notification (realtime)
            "test_notification__frequency": "realtime",
            # Using non-default for required_channel_notification (default is daily)
            "required_channel_notification__frequency": "realtime",
        }

        save_notification_preferences(self.user, form_data)

        # Only the non-default frequency should be saved
        frequencies = EmailFrequency.objects.filter(user=self.user)
        self.assertEqual(frequencies.count(), 1)
        self.assertEqual(frequencies.first().notification_type, "required_channel_notification")
        self.assertEqual(frequencies.first().frequency, "realtime")
