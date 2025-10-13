from django.contrib.auth import get_user_model
from django.test import TestCase

from generic_notifications.utils import get_notifications

from .test_helpers import create_notification_with_channels

User = get_user_model()


class NotificationPerformanceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        self.actor = User.objects.create_user(username="actor", email="actor@example.com", password="testpass")

        for i in range(5):
            create_notification_with_channels(
                user=self.user,
                actor=self.actor,
                notification_type="test_notification",
                subject=f"Test notification {i}",
                text=f"This is test notification {i}",
                url=f"/notification/{i}/",
            )

    def test_get_notifications_queries(self):
        """Test the number of queries made by get_notifications"""
        with self.assertNumQueries(1):
            notifications = get_notifications(self.user)
            # Force evaluation of the queryset
            list(notifications)

    def test_notification_actor_access(self):
        """Test that accessing actor doesn't cause additional queries"""
        notifications = list(get_notifications(self.user))

        with self.assertNumQueries(0):  # Should be 0 since actor is select_related
            for notification in notifications:
                if notification.actor:
                    _ = notification.actor.email

    def test_notification_template_rendering_queries(self):
        """Test queries when accessing notification attributes in template"""
        notifications = get_notifications(self.user)

        # First, evaluate the queryset
        notifications_list = list(notifications)

        # Now test accessing attributes - should be 0 queries if prefetched
        with self.assertNumQueries(0):
            for notification in notifications_list:
                # Simulate template access patterns
                _ = notification.is_read
                _ = notification.notification_type
                _ = notification.get_text()
                _ = notification.url
                _ = notification.added
                _ = notification.id

    def test_notification_target_access_queries(self):
        """Test queries when accessing notification.target in template"""
        # Create notifications with targets
        for i in range(5):
            create_notification_with_channels(
                user=self.user,
                actor=self.actor,
                notification_type="test_notification",
                subject=f"Test notification {i}",
                text=f"This is test notification {i}",
                target=self.actor,
            )

        # First, evaluate the queryset
        with self.assertNumQueries(2):  # 1 for notifications + 1 for targets
            notifications = get_notifications(self.user).prefetch_related("target")
            notifications_list = list(notifications)

        # Test accessing target - should be 0 queries since we prefetch target
        with self.assertNumQueries(0):
            for notification in notifications_list:
                if notification.target and hasattr(notification.target, "email"):
                    _ = notification.target.email

    def test_notification_target_relationship_access(self):
        """Test that accessing relationships through target causes additional queries"""
        # Create notifications where each has a different notification as its target
        for i in range(5):
            # Create the target notification
            target_notification = create_notification_with_channels(
                user=self.actor,
                notification_type="target_notification",
                subject=f"Target notification {i}",
                text=f"Target text {i}",
            )

            # Create notification pointing to it
            create_notification_with_channels(
                user=self.user,
                actor=self.actor,
                notification_type="test_notification",
                subject=f"Test notification {i}",
                text=f"This is test notification {i}",
                target=target_notification,
            )

        # First, evaluate the queryset
        with self.assertNumQueries(2):  # 1 for notifications + 1 for targets
            notifications = get_notifications(self.user).prefetch_related("target")
            notifications_list = list(notifications)

        # Test accessing target.recipient - this WILL cause N+1 queries
        # because we didn't prefetch the target__recipient relationship
        with self.assertNumQueries(5):  # 5 queries for recipient access
            for notification in notifications_list:
                if notification.target and hasattr(notification.target, "recipient"):
                    _ = notification.target.recipient.email

    def test_notification_target_relationship_preselect_access(self):
        """Test that accessing relationships through target causes additional queries"""
        # Create notifications where each has a different notification as its target
        for i in range(5):
            # Create the target notification
            target_notification = create_notification_with_channels(
                user=self.actor,
                notification_type="target_notification",
                subject=f"Target notification {i}",
                text=f"Target text {i}",
            )

            # Create notification pointing to it
            create_notification_with_channels(
                user=self.user,
                actor=self.actor,
                notification_type="test_notification",
                subject=f"Test notification {i}",
                text=f"This is test notification {i}",
                target=target_notification,
            )

        # First, evaluate the queryset
        with self.assertNumQueries(3):  # 1 for notifications + 1 for targets + 1 for target recipients
            notifications = get_notifications(self.user).prefetch_related("target__recipient")
            notifications_list = list(notifications)

        # Test accessing target.recipient - this won't cause N+1 queries
        # because we now prefetch the target__recipient relationship
        with self.assertNumQueries(0):
            for notification in notifications_list:
                if notification.target and hasattr(notification.target, "recipient"):
                    _ = notification.target.recipient.email

    def test_notification_mixed_targets_queries(self):
        """Test queries with heterogeneous notification.target"""
        # Create notifications with targets
        notification = create_notification_with_channels(
            user=self.user,
            actor=self.actor,
            notification_type="test_notification",
            subject="Test notification 1",
            text="This is test notification 1",
            target=self.actor,
        )

        create_notification_with_channels(
            user=self.user,
            actor=self.actor,
            notification_type="test_notification",
            subject="Test notification 2",
            text="This is test notification 2",
            target=notification,
        )

        # First, evaluate the queryset
        with self.assertNumQueries(1):
            notifications = get_notifications(self.user)
            _ = list(notifications)
