from django.contrib.auth import get_user_model
from django.test import TestCase

from generic_notifications.channels import WebsiteChannel
from generic_notifications.models import Notification
from generic_notifications.utils import get_notifications

User = get_user_model()


class NotificationPerformanceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="testpass")
        self.actor = User.objects.create_user(username="actor", email="actor@example.com", password="testpass")

        for i in range(5):
            Notification.objects.create(
                recipient=self.user,
                actor=self.actor,
                notification_type="test_notification",
                subject=f"Test notification {i}",
                text=f"This is test notification {i}",
                channels=[WebsiteChannel.key],
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
        Notification.objects.all().delete()
        for i in range(5):
            Notification.objects.create(
                recipient=self.user,
                actor=self.actor,
                notification_type="test_notification",
                subject=f"Test notification {i}",
                text=f"This is test notification {i}",
                channels=[WebsiteChannel.key],
                target=self.actor,
            )

        # First, evaluate the queryset
        notifications = get_notifications(self.user)
        notifications_list = list(notifications)

        # Test accessing target - this will cause queries
        with self.assertNumQueries(5):  # Expecting 5 queries
            for notification in notifications_list:
                if notification.target and hasattr(notification.target, "email"):
                    _ = notification.target.email
