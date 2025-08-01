from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from generic_notifications.frequencies import DailyFrequency, NotificationFrequency, RealtimeFrequency
from generic_notifications.models import EmailFrequency, Notification
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

User = get_user_model()


class WeeklyFrequency(NotificationFrequency):
    key = "weekly"
    name = "Weekly"
    is_realtime = False
    description = ""


class TestNotificationType(NotificationType):
    key = "test_type"
    name = "Test Type"
    description = ""
    default_email_frequency = DailyFrequency  # Defaults to daily like comments


class OtherNotificationType(NotificationType):
    key = "other_type"
    name = "Other Type"
    description = ""
    default_email_frequency = RealtimeFrequency  # Defaults to realtime like system messages


class SendDigestEmailsCommandTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", email="user1@example.com", password="testpass")
        self.user2 = User.objects.create_user(username="user2", email="user2@example.com", password="testpass")
        self.user3 = User.objects.create_user(username="user3", email="user3@example.com", password="testpass")

        # Register test data
        registry.register_type(TestNotificationType)
        registry.register_type(OtherNotificationType)

        # Re-register frequencies in case they were cleared by other tests
        registry.register_frequency(RealtimeFrequency, force=True)
        registry.register_frequency(DailyFrequency, force=True)
        registry.register_frequency(WeeklyFrequency)

    def tearDown(self):
        mail.outbox.clear()

    def test_dry_run_option(self):
        # Just test that dry-run option works without errors
        call_command("send_digest_emails", "--frequency", "daily", "--dry-run")

    def test_no_digest_frequencies(self):
        # Clear all frequencies and add only realtime
        registry.unregister_frequency(DailyFrequency)
        registry.register_frequency(RealtimeFrequency)

        # Should complete without sending any emails
        call_command("send_digest_emails", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 0)

    def test_target_frequency_not_found(self):
        # Should complete without error when frequency not found (logging is handled internally)
        call_command("send_digest_emails", "--frequency", "nonexistent")

    def test_target_frequency_is_realtime(self):
        # Should complete without error when frequency is realtime (logging is handled internally)
        call_command("send_digest_emails", "--frequency", "realtime")

    def test_send_digest_emails_basic_flow(self):
        # Set up user with daily frequency preference
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")

        # Create a notification
        notification = Notification.objects.create(
            recipient=self.user1,
            notification_type="test_type",
            subject="Test notification",
            text="This is a test notification",
            channels=["email"],
        )

        # No emails should be in outbox initially
        self.assertEqual(len(mail.outbox), 0)

        call_command("send_digest_emails", "--frequency", "daily")

        # Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check email details
        self.assertEqual(email.to, [self.user1.email])
        self.assertIn("1 new notifications", email.subject)
        self.assertIn("Test notification", email.body)

        # Verify notification was marked as sent
        notification.refresh_from_db()
        self.assertIsNotNone(notification.email_sent_at)

    def test_dry_run_does_not_send_emails(self):
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")

        notification = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Test notification", channels=["email"]
        )

        # Ensure no emails in outbox initially
        self.assertEqual(len(mail.outbox), 0)

        call_command("send_digest_emails", "--frequency", "daily", "--dry-run")

        # Should not send any emails in dry run
        self.assertEqual(len(mail.outbox), 0)

        # Notification should not be marked as sent
        notification.refresh_from_db()
        self.assertIsNone(notification.email_sent_at)

    def test_only_includes_unread_notifications(self):
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")

        # Create read and unread notifications
        read_notification = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Read notification", channels=["email"]
        )
        read_notification.mark_as_read()

        unread_notification = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Unread notification", channels=["email"]
        )

        call_command("send_digest_emails", "--frequency", "daily")

        # Should send one email with only unread notification
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Unread notification", email.body)
        self.assertNotIn("Read notification", email.body)

        # Only unread notification should be marked as sent
        read_notification.refresh_from_db()
        unread_notification.refresh_from_db()

        self.assertIsNone(read_notification.email_sent_at)  # Still not sent
        self.assertIsNotNone(unread_notification.email_sent_at)  # Now sent

    def test_only_includes_unsent_notifications(self):
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")

        # Create sent and unsent notifications
        Notification.objects.create(
            recipient=self.user1,
            notification_type="test_type",
            subject="Sent notification",
            email_sent_at=timezone.now(),
        )

        unsent_notification = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Unsent notification", channels=["email"]
        )

        call_command("send_digest_emails", "--frequency", "daily")

        # Should send one email with only unsent notification
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Unsent notification", email.body)
        self.assertNotIn("Sent notification", email.body)

        # Unsent notification should now be marked as sent
        unsent_notification.refresh_from_db()
        self.assertIsNotNone(unsent_notification.email_sent_at)

    def test_sends_all_unsent_notifications(self):
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")

        # Create notification older than time window (>1 day ago)
        old_notification = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Old notification", channels=["email"]
        )
        # Manually set old timestamp
        old_time = timezone.now() - timedelta(days=2)
        Notification.objects.filter(id=old_notification.id).update(added=old_time)

        # Create recent notification
        recent_notification = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Recent notification", channels=["email"]
        )

        call_command("send_digest_emails", "--frequency", "daily")

        # Should send one email with both notifications (no time window filtering)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Recent notification", email.body)
        self.assertIn("Old notification", email.body)
        self.assertIn("2 new notifications", email.subject)

        # Both notifications should be marked as sent
        old_notification.refresh_from_db()
        recent_notification.refresh_from_db()

        self.assertIsNotNone(old_notification.email_sent_at)  # Old but unsent, so included
        self.assertIsNotNone(recent_notification.email_sent_at)  # Recent, sent

    def test_specific_frequency_filter(self):
        # Set up users with different frequency preferences
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")
        EmailFrequency.objects.create(user=self.user2, notification_type="test_type", frequency="weekly")

        # Create notifications for both
        Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Daily user notification", channels=["email"]
        )
        Notification.objects.create(
            recipient=self.user2, notification_type="test_type", subject="Weekly user notification", channels=["email"]
        )

        call_command("send_digest_emails", "--frequency", "daily")

        # Should only send email to daily user
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])
        self.assertIn("Daily user notification", email.body)

        # Clear outbox and test weekly frequency
        mail.outbox.clear()
        call_command("send_digest_emails", "--frequency", "weekly")

        # Should only send email to weekly user
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user2.email])
        self.assertIn("Weekly user notification", email.body)

    def test_multiple_notification_types_for_user(self):
        # Set up user with multiple notification types for daily frequency
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")
        EmailFrequency.objects.create(user=self.user1, notification_type="other_type", frequency="daily")

        # Create notifications of both types
        notification1 = Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Test type notification", channels=["email"]
        )
        notification2 = Notification.objects.create(
            recipient=self.user1, notification_type="other_type", subject="Other type notification", channels=["email"]
        )

        call_command("send_digest_emails", "--frequency", "daily")

        # Should send one digest email with both notifications
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])
        self.assertIn("2 new notifications", email.subject)
        self.assertIn("Test type notification", email.body)
        self.assertIn("Other type notification", email.body)

        # Both notifications should be marked as sent
        notification1.refresh_from_db()
        notification2.refresh_from_db()
        self.assertIsNotNone(notification1.email_sent_at)
        self.assertIsNotNone(notification2.email_sent_at)

    def test_no_notifications_to_send(self):
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="daily")

        # No notifications created

        call_command("send_digest_emails", "--frequency", "daily")

        # Should not send any emails
        self.assertEqual(len(mail.outbox), 0)

    def test_users_with_disabled_email_channel_dont_get_digest(self):
        """Test that users who disabled email channel for a type don't get digest emails."""
        # With the new architecture, if email is disabled, notifications won't have email channel
        # So create a notification without email channel to simulate this
        Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Test notification", channels=["website"]
        )

        # Run daily digest - should not send anything (no email channel)
        call_command("send_digest_emails", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 0)

    def test_users_with_default_frequencies_get_digest(self):
        """Test that users without explicit preferences get digest emails based on default frequencies."""
        # Don't create any EmailFrequency preferences - user will use defaults

        # Create a test_type notification (defaults to daily)
        test_notification = Notification.objects.create(
            recipient=self.user1,
            notification_type="test_type",
            subject="Test notification",
            text="This is a test notification",
            channels=["email"],
        )

        # Create an other_type notification (defaults to realtime)
        other_notification = Notification.objects.create(
            recipient=self.user1,
            notification_type="other_type",
            subject="Other notification",
            text="This is another type of notification",
            channels=["email"],
        )

        # Run daily digest - should include comment but not system message
        call_command("send_digest_emails", "--frequency", "daily")

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])
        self.assertIn("Test notification", email.body)
        self.assertNotIn("Other notification", email.body)

        # Verify only test notification was marked as sent
        test_notification.refresh_from_db()
        other_notification.refresh_from_db()
        self.assertIsNotNone(test_notification.email_sent_at)
        self.assertIsNone(other_notification.email_sent_at)

    def test_mixed_explicit_and_default_preferences(self):
        """Test that users with some explicit preferences and some defaults work correctly."""
        # User explicitly sets test_type to weekly
        EmailFrequency.objects.create(user=self.user1, notification_type="test_type", frequency="weekly")
        # other_type will use its default (realtime)

        # Create notifications
        Notification.objects.create(
            recipient=self.user1, notification_type="test_type", subject="Test notification", channels=["email"]
        )
        Notification.objects.create(
            recipient=self.user1, notification_type="other_type", subject="Other notification", channels=["email"]
        )

        # Run daily digest - should get nothing (test_type is weekly, other_type is realtime)
        call_command("send_digest_emails", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 0)

        # Run weekly digest - should get test notification
        call_command("send_digest_emails", "--frequency", "weekly")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Test notification", email.body)
        self.assertNotIn("Other notification", email.body)

    def test_multiple_users_default_and_explicit_mix(self):
        """Test digest emails work correctly with multiple users having different preference configurations."""
        # user1: Uses all defaults (test_type=daily, other_type=realtime)
        # user2: Explicit preference (test_type=weekly, other_type uses default=realtime)
        # user3: Mixed (test_type=daily explicit, other_type uses default=realtime)

        EmailFrequency.objects.create(user=self.user2, notification_type="test_type", frequency="weekly")
        EmailFrequency.objects.create(user=self.user3, notification_type="test_type", frequency="daily")

        # Create test notifications for all users
        for i, user in enumerate([self.user1, self.user2, self.user3], 1):
            Notification.objects.create(
                recipient=user,
                notification_type="test_type",
                subject=f"Test notification for user {i}",
                channels=["email"],
            )

        # Run daily digest - should get user1 and user3 (both have test_type=daily)
        call_command("send_digest_emails", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 2)

        recipients = {email.to[0] for email in mail.outbox}
        self.assertIn(self.user1.email, recipients)
        self.assertIn(self.user3.email, recipients)
        self.assertNotIn(self.user2.email, recipients)

        # Clear outbox and run weekly digest - should get user2
        mail.outbox.clear()
        call_command("send_digest_emails", "--frequency", "weekly")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], self.user2.email)
        self.assertIn("Test notification for user 2", mail.outbox[0].body)
