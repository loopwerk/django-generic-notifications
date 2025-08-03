from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from generic_notifications import send_notification
from generic_notifications.channels import WebsiteChannel
from generic_notifications.models import Notification
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType
from generic_notifications.utils import get_notifications, get_unread_count, mark_notifications_as_read

User = get_user_model()


class TestNotificationType(NotificationType):
    key = "test_type"
    name = "Test Type"
    description = ""


class OtherNotificationType(NotificationType):
    key = "other_type"
    name = "Other Type"
    description = ""


class GroupingNotificationType(NotificationType):
    key = "grouping_type"
    name = "Grouping Type"
    description = "Notification that supports grouping"

    @classmethod
    def should_save(cls, notification):
        # Look for existing unread notification with same actor and target
        existing = Notification.objects.filter(
            recipient=notification.recipient,
            notification_type=notification.notification_type,
            actor=notification.actor,
            content_type_id=notification.content_type_id,
            object_id=notification.object_id,
            read__isnull=True,
        ).first()

        if existing:
            # Update count in metadata
            count = existing.metadata.get("count", 1)
            existing.metadata["count"] = count + 1
            existing.save()
            return False

        return True


class SendNotificationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        self.actor = User.objects.create_user(username="actor", email="actor@example.com", password="testpass")

        # Register test notification type
        self.notification_type = TestNotificationType
        registry.register_type(TestNotificationType)

    def test_send_notification_basic(self):
        notification = send_notification(
            recipient=self.user, notification_type=self.notification_type, subject="Test Subject", text="Test message"
        )

        self.assertIsInstance(notification, Notification)
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.notification_type, "test_type")
        self.assertEqual(notification.subject, "Test Subject")
        self.assertEqual(notification.text, "Test message")
        self.assertIsNone(notification.actor)
        self.assertIsNone(notification.target)

    def test_send_notification_with_actor_and_target(self):
        notification = send_notification(
            recipient=self.user,
            notification_type=self.notification_type,
            actor=self.actor,
            target=self.actor,  # Using actor as target for simplicity
            url="/test/url",
            metadata={"key": "value"},
        )

        self.assertEqual(notification.actor, self.actor)
        self.assertEqual(notification.target, self.actor)
        self.assertEqual(notification.url, "/test/url")
        self.assertEqual(notification.metadata, {"key": "value"})

    def test_send_notification_invalid_type(self):
        class InvalidNotificationType(NotificationType):
            key = "invalid_type"
            name = "Invalid Type"
            description = ""

        invalid_type = InvalidNotificationType
        with self.assertRaises(ValueError) as cm:
            send_notification(recipient=self.user, notification_type=invalid_type)

        self.assertIn("not registered", str(cm.exception))

    def test_send_notification_processes_channels(self):
        notification = send_notification(recipient=self.user, notification_type=self.notification_type)

        # Verify notification was created with channels
        self.assertIsNotNone(notification)
        self.assertIn("website", notification.channels)
        self.assertIn("email", notification.channels)
        self.assertEqual(notification.notification_type, "test_type")

    def test_send_notification_multiple_channels(self):
        notification = send_notification(recipient=self.user, notification_type=self.notification_type)

        # Notification should have both channels enabled
        self.assertIn("website", notification.channels)
        self.assertIn("email", notification.channels)
        self.assertEqual(len(notification.channels), 2)


class MarkNotificationsAsReadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        registry.register_type(TestNotificationType)

        # Create test notifications
        self.notification1 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="First"
        )
        self.notification2 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Second"
        )
        self.notification3 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Third"
        )

    def test_mark_all_notifications_as_read(self):
        # All should be unread initially
        self.assertFalse(self.notification1.is_read)
        self.assertFalse(self.notification2.is_read)
        self.assertFalse(self.notification3.is_read)

        mark_notifications_as_read(self.user)

        # Refresh from database
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        self.notification3.refresh_from_db()

        # All should now be read
        self.assertTrue(self.notification1.is_read)
        self.assertTrue(self.notification2.is_read)
        self.assertTrue(self.notification3.is_read)

    def test_mark_specific_notifications_as_read(self):
        notification_ids = [self.notification1.id, self.notification3.id]

        mark_notifications_as_read(self.user, notification_ids)

        # Refresh from database
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        self.notification3.refresh_from_db()

        # Only specified notifications should be read
        self.assertTrue(self.notification1.is_read)
        self.assertFalse(self.notification2.is_read)
        self.assertTrue(self.notification3.is_read)

    def test_mark_already_read_notifications(self):
        # Mark one as read first
        self.notification1.mark_as_read()
        original_read_time = self.notification1.read

        mark_notifications_as_read(self.user)

        self.notification1.refresh_from_db()
        # Read time should not change for already read notifications
        self.assertEqual(self.notification1.read, original_read_time)

    def test_mark_notifications_other_user_not_affected(self):
        other_user = User.objects.create_user(username="other", email="other@example.com", password="testpass")
        other_notification = Notification.objects.create(
            recipient=other_user, notification_type="test_type", channels=["website", "email"]
        )

        mark_notifications_as_read(self.user)

        other_notification.refresh_from_db()
        # Other user's notifications should not be affected
        self.assertFalse(other_notification.is_read)


class GetUnreadCountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        registry.register_type(TestNotificationType)

    def test_get_unread_count_empty(self):
        count = get_unread_count(self.user, channel=WebsiteChannel)
        self.assertEqual(count, 0)

    def test_get_unread_count_with_unread_notifications(self):
        # Create unread notifications
        Notification.objects.create(recipient=self.user, notification_type="test_type", channels=["website"])
        Notification.objects.create(recipient=self.user, notification_type="test_type", channels=["website"])
        Notification.objects.create(recipient=self.user, notification_type="test_type", channels=["website"])

        count = get_unread_count(self.user, channel=WebsiteChannel)
        self.assertEqual(count, 3)

    def test_get_unread_count_with_mix_of_read_unread(self):
        # Create mix of read and unread
        notification1 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website"]
        )
        Notification.objects.create(recipient=self.user, notification_type="test_type", channels=["website"])
        notification3 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", channels=["website"]
        )

        # Mark some as read
        notification1.mark_as_read()
        notification3.mark_as_read()

        count = get_unread_count(self.user, channel=WebsiteChannel)
        self.assertEqual(count, 1)

    def test_get_unread_count_other_user_not_counted(self):
        other_user = User.objects.create_user(username="other", email="other@example.com", password="testpass")

        # Create notifications for both users
        Notification.objects.create(recipient=self.user, notification_type="test_type", channels=["website"])
        Notification.objects.create(recipient=other_user, notification_type="test_type", channels=["website", "email"])

        count = get_unread_count(self.user, channel=WebsiteChannel)
        self.assertEqual(count, 1)


class GetNotificationsForUserTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        registry.register_type(TestNotificationType)
        registry.register_type(OtherNotificationType)

        # Create test notifications
        self.notification1 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test 1", channels=["website", "email"]
        )
        self.notification2 = Notification.objects.create(
            recipient=self.user, notification_type="other_type", subject="Other 1", channels=["website", "email"]
        )
        self.notification3 = Notification.objects.create(
            recipient=self.user, notification_type="test_type", subject="Test 2", channels=["website", "email"]
        )

        # Mark one as read
        self.notification2.mark_as_read()

    def test_get_all_notifications(self):
        notifications = get_notifications(self.user, channel=WebsiteChannel)

        self.assertEqual(notifications.count(), 3)
        # Should be ordered by -added (newest first)
        self.assertEqual(list(notifications), [self.notification3, self.notification2, self.notification1])

    def test_get_unread_only(self):
        notifications = get_notifications(self.user, channel=WebsiteChannel, unread_only=True)

        self.assertEqual(notifications.count(), 2)
        # Should not include the read notification
        self.assertIn(self.notification1, notifications)
        self.assertNotIn(self.notification2, notifications)
        self.assertIn(self.notification3, notifications)

    def test_get_with_limit(self):
        notifications = get_notifications(self.user, channel=WebsiteChannel, limit=2)

        self.assertEqual(notifications.count(), 2)
        # Should get the first 2 (newest)
        self.assertEqual(list(notifications), [self.notification3, self.notification2])

    def test_get_notifications_other_user_not_included(self):
        other_user = User.objects.create_user(username="other", email="other@example.com", password="testpass")
        Notification.objects.create(recipient=other_user, notification_type="test_type", channels=["website", "email"])

        notifications = get_notifications(self.user, channel=WebsiteChannel)

        self.assertEqual(notifications.count(), 3)  # Only this user's notifications


class NotificationGroupingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        self.actor = User.objects.create_user(username="actor", email="actor@example.com", password="testpass")
        self.target = User.objects.create_user(username="target", email="target@example.com", password="testpass")

        # Register the grouping notification type
        registry.register_type(GroupingNotificationType)

    def test_should_save_grouping_behavior(self):
        # First notification should be created
        notification1 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
            text="First comment",
        )

        self.assertIsNotNone(notification1)

        # Second notification should be grouped
        notification2 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
            text="Second comment",
        )

        # No new notification created
        self.assertIsNone(notification2)

        # Original notification should be updated
        notification1.refresh_from_db()
        self.assertEqual(notification1.metadata["count"], 2)

        # Still only one notification in database
        self.assertEqual(Notification.objects.filter(recipient=self.user, notification_type="grouping_type").count(), 1)

    def test_grouping_with_different_actors(self):
        actor2 = User.objects.create_user(username="actor2", email="actor2@example.com", password="testpass")

        # First notification
        notification1 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
        )

        # Different actor - should create new notification
        notification2 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=actor2,
            target=self.target,
        )

        self.assertIsNotNone(notification1)
        self.assertIsNotNone(notification2)
        self.assertNotEqual(notification1.id, notification2.id)
        self.assertEqual(Notification.objects.filter(recipient=self.user, notification_type="grouping_type").count(), 2)

    def test_grouping_with_different_targets(self):
        target2 = User.objects.create_user(username="target2", email="target2@example.com", password="testpass")

        # First notification
        notification1 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
        )

        # Different target - should create new notification
        notification2 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=target2,
        )

        self.assertIsNotNone(notification1)
        self.assertIsNotNone(notification2)
        self.assertNotEqual(notification1.id, notification2.id)
        self.assertEqual(Notification.objects.filter(recipient=self.user, notification_type="grouping_type").count(), 2)

    def test_grouping_ignores_read_notifications(self):
        # First notification
        notification1 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
        )

        # Mark it as read
        notification1.mark_as_read()

        # Second notification should create new one (not group with read notification)
        notification2 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
        )

        self.assertIsNotNone(notification1)
        self.assertIsNotNone(notification2)
        self.assertNotEqual(notification1.id, notification2.id)

    def test_grouping_updates_metadata_multiple_times(self):
        # Create first notification
        notification1 = send_notification(
            recipient=self.user,
            notification_type=GroupingNotificationType,
            actor=self.actor,
            target=self.target,
        )

        # Send 3 more notifications
        for i in range(3):
            result = send_notification(
                recipient=self.user,
                notification_type=GroupingNotificationType,
                actor=self.actor,
                target=self.target,
            )
            self.assertIsNone(result)

        # Check count was incremented correctly
        notification1.refresh_from_db()
        self.assertEqual(notification1.metadata["count"], 4)

    @patch("generic_notifications.types.NotificationType.should_save")
    def test_transaction_atomicity(self, mock_should_save):
        # Simulate should_save raising an exception
        mock_should_save.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            send_notification(
                recipient=self.user,
                notification_type=TestNotificationType,
                actor=self.actor,
                target=self.target,
            )

        # No notification should be created due to transaction rollback
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 0)
