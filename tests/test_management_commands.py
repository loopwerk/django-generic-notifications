from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from generic_notifications.channels import EmailChannel
from generic_notifications.frequencies import BaseFrequency, DailyFrequency, RealtimeFrequency
from generic_notifications.models import Notification, NotificationFrequencyPreference
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

from .test_helpers import create_notification_with_channels

User = get_user_model()


class WeeklyFrequency(BaseFrequency):
    key = "weekly"
    name = "Weekly"
    is_realtime = False
    description = ""


class TestNotificationType(NotificationType):
    key = "test_type"
    name = "Test Type"
    description = ""
    default_frequency = DailyFrequency  # Defaults to daily like comments


class OtherNotificationType(NotificationType):
    key = "other_type"
    name = "Other Type"
    description = ""
    default_frequency = RealtimeFrequency  # Defaults to realtime like system messages


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
        call_command("send_notification_digests", "--frequency", "daily", "--dry-run")

    def test_no_digest_frequencies(self):
        # Clear all frequencies and add only realtime
        registry.unregister_frequency(DailyFrequency)
        registry.register_frequency(RealtimeFrequency)

        # Should complete without sending any emails
        call_command("send_notification_digests", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 0)

    def test_target_frequency_not_found(self):
        # Should complete without error when frequency not found (logging is handled internally)
        call_command("send_notification_digests", "--frequency", "nonexistent")

    def test_target_frequency_is_realtime(self):
        # Should complete without error when frequency is realtime (logging is handled internally)
        call_command("send_notification_digests", "--frequency", "realtime")

    def test_send_digest_emails_basic_flow(self):
        # Set up user with daily frequency preference
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )

        # Create a notification
        notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Test notification",
            text="This is a test notification",
        )

        # No emails should be in outbox initially
        self.assertEqual(len(mail.outbox), 0)

        call_command("send_notification_digests", "--frequency", "daily")

        # Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check email details
        self.assertEqual(email.to, [self.user1.email])
        self.assertEqual(email.subject, "Daily digest - 1 new notification")
        self.assertEqual(email.body, "You have 1 new notification:\n\n- This is a test notification")

        # Verify notification was marked as sent
        notification.refresh_from_db()

        self.assertTrue(notification.is_sent_on_channel(EmailChannel))

    def test_dry_run_does_not_send_emails(self):
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )

        notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Test notification",
        )

        # Ensure no emails in outbox initially
        self.assertEqual(len(mail.outbox), 0)

        call_command("send_notification_digests", "--frequency", "daily", "--dry-run")

        # Should not send any emails in dry run
        self.assertEqual(len(mail.outbox), 0)

        # Notification should not be marked as sent
        notification.refresh_from_db()

        self.assertFalse(notification.is_sent_on_channel(EmailChannel))

    def test_only_includes_unread_notifications(self):
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )

        # Create read and unread notifications
        read_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Read notification subject",
            text="Read notification text",
        )
        read_notification.mark_as_read()

        unread_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Unread notification subject",
            text="Unread notification text",
        )

        call_command("send_notification_digests", "--frequency", "daily")

        # Should send one email with only unread notification
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.body, "You have 1 new notification:\n\n- Unread notification text")

        # Only unread notification should be marked as sent
        read_notification.refresh_from_db()
        unread_notification.refresh_from_db()

        self.assertFalse(read_notification.is_sent_on_channel(EmailChannel))  # Still not sent
        self.assertTrue(unread_notification.is_sent_on_channel(EmailChannel))  # Now sent

    def test_only_includes_unsent_notifications(self):
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )

        # Create sent and unsent notifications
        sent_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Sent notification",
        )
        # Mark as sent
        sent_notification.mark_sent_on_channel(EmailChannel)

        unsent_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Unsent notification subject",
            text="Unsent notification text",
        )

        call_command("send_notification_digests", "--frequency", "daily")

        # Should send one email with only unsent notification
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.body, "You have 1 new notification:\n\n- Unsent notification text")

        # Unsent notification should now be marked as sent
        unsent_notification.refresh_from_db()

        self.assertTrue(unsent_notification.is_sent_on_channel(EmailChannel))

    def test_sends_all_unsent_notifications(self):
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )

        # Create notification older than time window (>1 day ago)
        old_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Old notification subject",
            text="Old notification text",
        )
        # Manually set old timestamp
        old_time = timezone.now() - timedelta(days=2)
        Notification.objects.filter(id=old_notification.id).update(added=old_time)

        # Create recent notification
        recent_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Recent notification subject",
            text="Recent notification text",
        )

        call_command("send_notification_digests", "--frequency", "daily")

        # Should send one email with both notifications (no time window filtering)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Daily digest - 2 new notifications")
        self.assertEqual(
            email.body, "You have 2 new notifications:\n\n- Recent notification text\n- Old notification text"
        )

        # Both notifications should be marked as sent
        old_notification.refresh_from_db()
        recent_notification.refresh_from_db()

        self.assertTrue(old_notification.is_sent_on_channel(EmailChannel))  # Old but unsent, so included
        self.assertTrue(recent_notification.is_sent_on_channel(EmailChannel))  # Recent, sent

    def test_specific_frequency_filter(self):
        # Set up users with different frequency preferences
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )
        NotificationFrequencyPreference.objects.create(
            user=self.user2, notification_type="test_type", frequency="weekly"
        )

        # Create notifications for both
        create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Daily user notification subject",
            text="Daily user notification text",
        )
        create_notification_with_channels(
            user=self.user2,
            notification_type="test_type",
            subject="Weekly user notification subject",
            text="Weekly user notification text",
        )

        call_command("send_notification_digests", "--frequency", "daily")

        # Should only send email to daily user
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])
        self.assertEqual(email.body, "You have 1 new notification:\n\n- Daily user notification text")

        # Clear outbox and test weekly frequency
        mail.outbox.clear()
        call_command("send_notification_digests", "--frequency", "weekly")

        # Should only send email to weekly user
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user2.email])
        self.assertEqual(email.body, "You have 1 new notification:\n\n- Weekly user notification text")

    def test_multiple_notification_types_for_user(self):
        # Set up user with multiple notification types for daily frequency
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="other_type", frequency="daily"
        )

        # Create notifications of both types
        notification1 = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Test type notification subject",
            text="Test type notification text",
        )
        notification2 = create_notification_with_channels(
            user=self.user1,
            notification_type="other_type",
            subject="Other type notification subject",
            text="Other type notification text",
        )

        call_command("send_notification_digests", "--frequency", "daily")

        # Should send one digest email with both notifications
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])
        self.assertEqual(email.subject, "Daily digest - 2 new notifications")
        self.assertEqual(
            email.body, "You have 2 new notifications:\n\n- Other type notification text\n- Test type notification text"
        )

        # Both notifications should be marked as sent
        notification1.refresh_from_db()
        notification2.refresh_from_db()

        self.assertTrue(notification1.is_sent_on_channel(EmailChannel))
        self.assertTrue(notification2.is_sent_on_channel(EmailChannel))

    def test_no_notifications_to_send(self):
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="daily"
        )

        # No notifications created

        call_command("send_notification_digests", "--frequency", "daily")

        # Should not send any emails
        self.assertEqual(len(mail.outbox), 0)

    def test_users_with_disabled_email_channel_dont_get_digest(self):
        """Test that users who disabled email channel for a type don't get digest emails."""
        # With the new architecture, if email is disabled, notifications won't have email channel
        # So create a notification without email channel to simulate this
        create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Test notification",
            channels=["website"],
        )

        # Run daily digest - should not send anything (no email channel)
        call_command("send_notification_digests", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 0)

    def test_users_with_default_frequencies_get_digest(self):
        """Test that users without explicit preferences get digest emails based on default frequencies."""
        # Don't create any NotificationFrequencyPreference preferences - user will use defaults

        # Create a test_type notification (defaults to daily)
        test_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Test notification",
            text="This is a test notification",
        )

        # Create an other_type notification (defaults to realtime)
        other_notification = create_notification_with_channels(
            user=self.user1,
            notification_type="other_type",
            subject="Other notification",
            text="This is another type of notification",
        )

        # Run daily digest - should include comment but not system message
        call_command("send_notification_digests", "--frequency", "daily")

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user1.email])
        self.assertEqual(email.body, "You have 1 new notification:\n\n- This is a test notification")

        # Verify only test notification was marked as sent
        test_notification.refresh_from_db()
        other_notification.refresh_from_db()

        self.assertTrue(test_notification.is_sent_on_channel(EmailChannel))
        self.assertFalse(other_notification.is_sent_on_channel(EmailChannel))

    def test_mixed_explicit_and_default_preferences(self):
        """Test that users with some explicit preferences and some defaults work correctly."""
        # User explicitly sets test_type to weekly
        NotificationFrequencyPreference.objects.create(
            user=self.user1, notification_type="test_type", frequency="weekly"
        )
        # other_type will use its default (realtime)

        # Create notifications
        create_notification_with_channels(
            user=self.user1,
            notification_type="test_type",
            subject="Test notification subject",
            text="Test notification text",
        )
        create_notification_with_channels(
            user=self.user1,
            notification_type="other_type",
            subject="Other notification subject",
            text="Other notification text",
        )

        # Run daily digest - should get nothing (test_type is weekly, other_type is realtime)
        call_command("send_notification_digests", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 0)

        # Run weekly digest - should get test notification
        call_command("send_notification_digests", "--frequency", "weekly")
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.body, "You have 1 new notification:\n\n- Test notification text")

    def test_multiple_users_default_and_explicit_mix(self):
        """Test digest emails work correctly with multiple users having different preference configurations."""
        # user1: Uses all defaults (test_type=daily, other_type=realtime)
        # user2: Explicit preference (test_type=weekly, other_type uses default=realtime)
        # user3: Mixed (test_type=daily explicit, other_type uses default=realtime)

        NotificationFrequencyPreference.objects.create(
            user=self.user2, notification_type="test_type", frequency="weekly"
        )
        NotificationFrequencyPreference.objects.create(
            user=self.user3, notification_type="test_type", frequency="daily"
        )

        # Create test notifications for all users
        for i, user in enumerate([self.user1, self.user2, self.user3], 1):
            create_notification_with_channels(
                user=user,
                notification_type="test_type",
                subject=f"Test notification for user {i} subject",
                text=f"Test notification for user {i} text",
            )

        # Run daily digest - should get user1 and user3 (both have test_type=daily)
        call_command("send_notification_digests", "--frequency", "daily")
        self.assertEqual(len(mail.outbox), 2)

        recipients = {email.to[0] for email in mail.outbox}
        self.assertEqual(set(recipients), {self.user1.email, self.user3.email})

        # Clear outbox and run weekly digest - should get user2
        mail.outbox.clear()
        call_command("send_notification_digests", "--frequency", "weekly")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], self.user2.email)
        self.assertEqual(mail.outbox[0].body, "You have 1 new notification:\n\n- Test notification for user 2 text")
