from django.test import TestCase

from generic_notifications.channels import BaseChannel
from generic_notifications.frequencies import BaseFrequency
from generic_notifications.registry import NotificationRegistry
from generic_notifications.types import NotificationType


class TestNotificationType(NotificationType):
    key = "test_key"
    name = "Test Name"
    description = ""


class TestNotificationTypeWithDescription(NotificationType):
    key = "test_key"
    name = "Test Name"
    description = "Custom description"


class NotificationTypeTest(TestCase):
    def test_create_notification_type(self):
        notification_type = TestNotificationType()

        self.assertEqual(notification_type.key, "test_key")
        self.assertEqual(notification_type.name, "Test Name")
        self.assertEqual(notification_type.description, "")  # empty by default

    def test_create_notification_type_with_description(self):
        notification_type = TestNotificationTypeWithDescription()

        self.assertEqual(notification_type.key, "test_key")
        self.assertEqual(notification_type.name, "Test Name")
        self.assertEqual(notification_type.description, "Custom description")

    def test_notification_type_str(self):
        notification_type = TestNotificationType()
        self.assertEqual(str(notification_type), "Test Name")


class TestRealtimeFrequency(BaseFrequency):
    key = "realtime"
    name = "Realtime"
    is_realtime = True
    description = ""


class TestDailyFrequency(BaseFrequency):
    key = "daily"
    name = "Daily"
    is_realtime = False
    description = ""


class TestWeeklyFrequency(BaseFrequency):
    key = "weekly"
    name = "Weekly"
    is_realtime = False
    description = "Once per week"


class TestDefaultFrequency(BaseFrequency):
    key = "test"
    name = "Test"
    is_realtime = False
    description = ""


class NotificationFrequencyTest(TestCase):
    def test_create_frequency_choice_realtime(self):
        frequency = TestRealtimeFrequency()

        self.assertEqual(frequency.key, "realtime")
        self.assertEqual(frequency.name, "Realtime")
        self.assertTrue(frequency.is_realtime)
        self.assertEqual(frequency.description, "")  # empty by default

    def test_create_frequency_choice_digest(self):
        frequency = TestDailyFrequency()

        self.assertEqual(frequency.key, "daily")
        self.assertEqual(frequency.name, "Daily")
        self.assertFalse(frequency.is_realtime)

    def test_create_frequency_choice_with_description(self):
        frequency = TestWeeklyFrequency()

        self.assertEqual(frequency.key, "weekly")
        self.assertEqual(frequency.name, "Weekly")
        self.assertEqual(frequency.description, "Once per week")

    def test_frequency_choice_defaults(self):
        frequency = TestDefaultFrequency()

        self.assertFalse(frequency.is_realtime)  # defaults to False
        self.assertEqual(frequency.description, "")  # empty by default

    def test_frequency_choice_str(self):
        frequency = TestDailyFrequency()
        self.assertEqual(str(frequency), "Daily")


class NotificationRegistryTest(TestCase):
    def setUp(self):
        self.registry = NotificationRegistry()

    def test_create_empty_registry(self):
        self.assertEqual(len(self.registry.get_all_types()), 0)
        self.assertEqual(len(self.registry.get_all_channels()), 0)
        self.assertEqual(len(self.registry.get_all_frequencies()), 0)

    def test_register_notification_type(self):
        self.registry.register_type(TestNotificationType)

        # Registry returns instances, but they should be equal in content
        registered_type = self.registry.get_type("test_key")
        self.assertEqual(registered_type.key, "test_key")
        self.assertEqual(registered_type.name, "Test Name")
        self.assertEqual(len(self.registry.get_all_types()), 1)

    def test_register_invalid_notification_type(self):
        with self.assertRaises(ValueError) as cm:
            self.registry.register_type("not_a_type_object")  # type: ignore[arg-type]

        self.assertIn("Must register a NotificationType subclass", str(cm.exception))

    def test_register_channel(self):
        class TestChannel(BaseChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        self.registry.register_channel(TestChannel)

        # Registry returns instances
        registered_channel = self.registry.get_channel("test")
        self.assertEqual(registered_channel.key, "test")
        self.assertEqual(registered_channel.name, "Test")
        self.assertEqual(len(self.registry.get_all_channels()), 1)

    def test_register_invalid_channel(self):
        with self.assertRaises(ValueError) as cm:
            self.registry.register_channel("not_a_channel_object")  # type: ignore[arg-type]

        self.assertIn("Must register a BaseChannel subclass", str(cm.exception))

    def test_register_frequency(self):
        self.registry.register_frequency(TestDailyFrequency)

        # Registry returns instances
        registered_frequency = self.registry.get_frequency("daily")
        self.assertEqual(registered_frequency.key, "daily")
        self.assertEqual(registered_frequency.name, "Daily")
        self.assertEqual(len(self.registry.get_all_frequencies()), 1)

    def test_register_invalid_frequency(self):
        with self.assertRaises(ValueError) as cm:
            self.registry.register_frequency("not_a_frequency_object")  # type: ignore[arg-type]

        self.assertIn("Must register a BaseFrequency subclass", str(cm.exception))

    def test_get_nonexistent_items(self):
        with self.assertRaises(KeyError):
            self.registry.get_type("nonexistent")
        with self.assertRaises(KeyError):
            self.registry.get_channel("nonexistent")
        with self.assertRaises(KeyError):
            self.registry.get_frequency("nonexistent")

    def test_get_realtime_frequencies(self):
        self.registry.register_frequency(TestRealtimeFrequency)
        self.registry.register_frequency(TestDailyFrequency)

        realtime_frequencies = self.registry.get_realtime_frequencies()

        self.assertEqual(len(realtime_frequencies), 1)
        self.assertEqual(realtime_frequencies[0].key, "realtime")
        self.assertTrue(realtime_frequencies[0].is_realtime)

    def test_get_realtime_frequencies_empty(self):
        self.registry.register_frequency(TestDailyFrequency)

        realtime_frequencies = self.registry.get_realtime_frequencies()

        self.assertEqual(len(realtime_frequencies), 0)

    def test_unregister_type(self):
        self.registry.register_type(TestNotificationType)

        # Verify it's registered
        self.assertIsNotNone(self.registry.get_type("test_key"))

        # Unregister it
        result = self.registry.unregister_type(TestNotificationType)

        self.assertTrue(result)
        with self.assertRaises(KeyError):
            self.registry.get_type("test_key")
        self.assertEqual(len(self.registry.get_all_types()), 0)

    def test_unregister_type_nonexistent(self):
        class NonexistentType(NotificationType):
            key = "nonexistent"
            name = "Nonexistent Type"
            description = ""

        result = self.registry.unregister_type(NonexistentType)
        self.assertFalse(result)

    def test_unregister_channel(self):
        class TestChannel(BaseChannel):
            key = "test"
            name = "Test"

            def process(self, notification):
                pass

        self.registry.register_channel(TestChannel)

        # Verify it's registered
        self.assertIsNotNone(self.registry.get_channel("test"))

        # Unregister it
        result = self.registry.unregister_channel(TestChannel)

        self.assertTrue(result)
        with self.assertRaises(KeyError):
            self.registry.get_channel("test")
        self.assertEqual(len(self.registry.get_all_channels()), 0)

    def test_unregister_channel_nonexistent(self):
        class NonexistentChannel(BaseChannel):
            key = "nonexistent"
            name = "Nonexistent Channel"

            def process(self, notification):
                pass

        result = self.registry.unregister_channel(NonexistentChannel)
        self.assertFalse(result)

    def test_unregister_frequency(self):
        self.registry.register_frequency(TestDailyFrequency)

        # Verify it's registered
        self.assertIsNotNone(self.registry.get_frequency("daily"))

        # Unregister it
        result = self.registry.unregister_frequency(TestDailyFrequency)

        self.assertTrue(result)
        with self.assertRaises(KeyError):
            self.registry.get_frequency("daily")
        self.assertEqual(len(self.registry.get_all_frequencies()), 0)

    def test_unregister_frequency_nonexistent(self):
        class NonexistentFrequency(BaseFrequency):
            key = "nonexistent"
            name = "Nonexistent Frequency"
            is_realtime = False
            description = ""

        result = self.registry.unregister_frequency(NonexistentFrequency)
        self.assertFalse(result)

    def test_clear_types(self):
        # Register some types
        class Type1(NotificationType):
            key = "type1"
            name = "Type 1"
            description = ""

        class Type2(NotificationType):
            key = "type2"
            name = "Type 2"
            description = ""

        self.registry.register_type(Type1)
        self.registry.register_type(Type2)

        self.assertEqual(len(self.registry.get_all_types()), 2)

        # Clear all types
        self.registry.clear_types()

        self.assertEqual(len(self.registry.get_all_types()), 0)
        with self.assertRaises(KeyError):
            self.registry.get_type("type1")
        with self.assertRaises(KeyError):
            self.registry.get_type("type2")

    def test_clear_channels(self):
        class Channel1(BaseChannel):
            key = "channel1"
            name = "Channel 1"

            def process(self, notification):
                pass

        class Channel2(BaseChannel):
            key = "channel2"
            name = "Channel 2"

            def process(self, notification):
                pass

        # Register some channels
        self.registry.register_channel(Channel1)
        self.registry.register_channel(Channel2)

        self.assertEqual(len(self.registry.get_all_channels()), 2)

        # Clear all channels
        self.registry.clear_channels()

        self.assertEqual(len(self.registry.get_all_channels()), 0)
        with self.assertRaises(KeyError):
            self.registry.get_channel("channel1")
        with self.assertRaises(KeyError):
            self.registry.get_channel("channel2")

    def test_clear_frequencies(self):
        class Freq1(BaseFrequency):
            key = "freq1"
            name = "Frequency 1"
            is_realtime = False
            description = ""

        class Freq2(BaseFrequency):
            key = "freq2"
            name = "Frequency 2"
            is_realtime = False
            description = ""

        # Register some frequencies
        self.registry.register_frequency(Freq1)
        self.registry.register_frequency(Freq2)

        self.assertEqual(len(self.registry.get_all_frequencies()), 2)

        # Clear all frequencies
        self.registry.clear_frequencies()

        self.assertEqual(len(self.registry.get_all_frequencies()), 0)
        with self.assertRaises(KeyError):
            self.registry.get_frequency("freq1")
        with self.assertRaises(KeyError):
            self.registry.get_frequency("freq2")

    def test_multiple_registrations_replace(self):
        class Type1(NotificationType):
            key = "test_type"
            name = "Test Type 1"
            description = ""

        class Type2(NotificationType):
            key = "test_type"
            name = "Test Type 2"
            description = ""

        # Register a type
        self.registry.register_type(Type1)

        # Register another type with same key (should replace)
        self.registry.register_type(Type2)

        # Should have the second type
        registered_type = self.registry.get_type("test_type")
        self.assertEqual(registered_type.name, "Test Type 2")
        self.assertEqual(len(self.registry.get_all_types()), 1)

    def test_get_all_methods_return_lists(self):
        # Test that get_all methods return lists, not dict values
        self.registry.register_type(TestNotificationType)

        types = self.registry.get_all_types()
        self.assertIsInstance(types, list)
        self.assertEqual(types[0].key, "test_key")

    def test_registry_isolation(self):
        # Create two different registry instances
        registry1 = NotificationRegistry()
        registry2 = NotificationRegistry()

        # Register type in first registry only
        registry1.register_type(TestNotificationType)

        # Should not affect second registry
        self.assertIsNotNone(registry1.get_type("test_key"))
        with self.assertRaises(KeyError):
            registry2.get_type("test_key")
