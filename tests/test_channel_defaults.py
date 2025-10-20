from django.contrib.auth import get_user_model
from django.test import TestCase

from generic_notifications.channels import BaseChannel, EmailChannel, WebsiteChannel
from generic_notifications.channels import register as register_channel
from generic_notifications.models import NotificationTypeChannelPreference
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

User = get_user_model()


class TestChannelDefaults(TestCase):
    """Test the new default channel behavior"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="defaults_test", email="defaults@example.com", password="testpass")

    def setUp(self):
        NotificationTypeChannelPreference.objects.filter(user=self.user).delete()

    def test_global_defaults_vs_explicit_defaults(self):
        """Test both global defaults (None) and explicit default_channels"""

        class GlobalDefaultType(NotificationType):
            key = "global_default"
            name = "Global Default"
            default_channels = None  # Use global defaults

        class ExplicitDefaultType(NotificationType):
            key = "explicit_default"
            name = "Explicit Default"
            default_channels = [WebsiteChannel]  # Only website

        registry.register_type(GlobalDefaultType)
        registry.register_type(ExplicitDefaultType)

        # Global defaults should include all enabled_by_default=True channels
        global_channels = GlobalDefaultType.get_enabled_channels(self.user)
        global_keys = [ch.key for ch in global_channels]
        self.assertIn(WebsiteChannel.key, global_keys)
        self.assertIn(EmailChannel.key, global_keys)

        # Explicit defaults should only include specified channels
        explicit_channels = ExplicitDefaultType.get_enabled_channels(self.user)
        explicit_keys = [ch.key for ch in explicit_channels]
        self.assertIn(WebsiteChannel.key, explicit_keys)
        self.assertNotIn(EmailChannel.key, explicit_keys)

    def test_required_and_forbidden_channel_interactions(self):
        """Test how required/forbidden channels interact with defaults"""

        # First create a custom channel that's disabled by default
        @register_channel
        class CustomRequiredChannel(BaseChannel):
            key = "custom_required"
            name = "Custom Required"
            enabled_by_default = False

            def send_now(self, notification):
                pass

        class ComplexType(NotificationType):
            key = "complex_type"
            name = "Complex Type"
            required_channels = [CustomRequiredChannel]  # Force inclusion of normally-disabled channel
            forbidden_channels = [WebsiteChannel]  # Force exclusion of normally-enabled channel

        registry.register_type(ComplexType)

        enabled_channels = ComplexType.get_enabled_channels(self.user)
        enabled_keys = [ch.key for ch in enabled_channels]

        self.assertEqual(len(enabled_keys), 2)
        # Required channel should be included even though disabled by default
        self.assertIn(CustomRequiredChannel.key, enabled_keys)
        # Forbidden channel should be excluded even though enabled by default
        self.assertNotIn(WebsiteChannel.key, enabled_keys)
        # EmailChannel should still be included (default behavior)
        self.assertIn(EmailChannel.key, enabled_keys)

    def test_user_overrides_and_empty_defaults(self):
        """Test user can disable defaults and empty default_channels works"""

        class EmptyDefaultType(NotificationType):
            key = "empty_default"
            name = "Empty Default"
            default_channels = []  # No defaults
            required_channels = [EmailChannel]  # But required email

        class DisableableType(NotificationType):
            key = "disableable"
            name = "Disableable"
            default_channels = [WebsiteChannel, EmailChannel]

        registry.register_type(EmptyDefaultType)
        registry.register_type(DisableableType)

        # Empty defaults should only have required channels
        empty_channels = EmptyDefaultType.get_enabled_channels(self.user)
        empty_keys = [ch.key for ch in empty_channels]
        self.assertEqual(len(empty_channels), 1)
        self.assertIn(EmailChannel.key, empty_keys)

        # User should be able to disable default channels
        NotificationTypeChannelPreference.objects.create(
            user=self.user, notification_type=DisableableType.key, channel=EmailChannel.key, enabled=False
        )

        disableable_channels = DisableableType.get_enabled_channels(self.user)
        disableable_keys = [ch.key for ch in disableable_channels]
        self.assertIn(WebsiteChannel.key, disableable_keys)
        self.assertNotIn(EmailChannel.key, disableable_keys)

    def test_custom_channel_enabled_by_default_false(self):
        """Test custom channels with enabled_by_default=False"""

        @register_channel
        class CustomChannel(BaseChannel):
            key = "custom_disabled"
            name = "Custom Disabled"
            enabled_by_default = False

            def send_now(self, notification):
                pass

        class GlobalDefaultType(NotificationType):
            key = "uses_global"
            name = "Uses Global"

        class ExplicitCustomType(NotificationType):
            key = "uses_custom"
            name = "Uses Custom"
            default_channels = [CustomChannel]

        registry.register_type(GlobalDefaultType)
        registry.register_type(ExplicitCustomType)

        # Global defaults shouldn't include disabled-by-default channels
        global_channels = GlobalDefaultType.get_enabled_channels(self.user)
        global_keys = [ch.key for ch in global_channels]
        self.assertNotIn(CustomChannel.key, global_keys)

        # Explicit defaults can include disabled-by-default channels
        custom_channels = ExplicitCustomType.get_enabled_channels(self.user)
        custom_keys = [ch.key for ch in custom_channels]
        self.assertIn(CustomChannel.key, custom_keys)
        self.assertNotIn(WebsiteChannel.key, custom_keys)  # Not in explicit list
