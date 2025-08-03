import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.management.base import BaseCommand

from generic_notifications.channels import EmailChannel
from generic_notifications.frequencies import NotificationFrequency
from generic_notifications.models import Notification
from generic_notifications.registry import registry
from generic_notifications.types import NotificationType

User = get_user_model()


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send digest emails to users who have opted for digest delivery"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without actually sending emails",
        )
        parser.add_argument(
            "--frequency",
            type=str,
            required=True,
            help="Process specific frequency (e.g., daily, weekly)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        target_frequency = options["frequency"]

        # In dry-run mode, temporarily set logger to INFO level for visibility
        original_level = None
        if dry_run:
            original_level = logger.level
            logger.setLevel(logging.INFO)
            logger.info("DRY RUN - No emails will be sent")

        # Verify email channel is registered
        try:
            registry.get_channel(EmailChannel.key)
        except KeyError:
            logger.error("Email channel not registered")
            return

        # Setup
        all_notification_types = registry.get_all_types()

        # Get the specific frequency (required argument)
        try:
            frequency_cls = registry.get_frequency(target_frequency)
        except KeyError:
            logger.error(f"Frequency '{target_frequency}' not found")
            return

        if frequency_cls.is_realtime:
            logger.error(f"Frequency '{target_frequency}' is realtime, not a digest frequency")
            return

        total_emails_sent = 0

        logger.info(f"Processing {frequency_cls.name} digests...")

        # Find all users who have unsent, unread notifications for email channel
        users_with_notifications = User.objects.filter(
            notifications__email_sent_at__isnull=True,
            notifications__read__isnull=True,
            notifications__channels__icontains=f'"{EmailChannel.key}"',
        ).distinct()

        for user in users_with_notifications:
            # Determine which notification types should use this frequency for this user
            relevant_types = self.get_notification_types_for_frequency(user, frequency_cls, all_notification_types)

            if not relevant_types:
                continue

            # Get unsent notifications for these types
            # Exclude read notifications - don't email what user already saw on website
            relevant_type_keys = [nt.key for nt in relevant_types]
            notifications = Notification.objects.filter(
                recipient=user,
                notification_type__in=relevant_type_keys,
                email_sent_at__isnull=True,
                read__isnull=True,
                channels__icontains=f'"{EmailChannel.key}"',
            ).order_by("-added")

            if notifications.exists():
                logger.info(
                    f"  User {user.email}: {notifications.count()} notifications for {frequency_cls.name} digest"
                )

                if not dry_run:
                    EmailChannel.send_digest_emails(user, notifications, frequency_cls)

                total_emails_sent += 1

                # List notification subjects for debugging
                for notification in notifications[:3]:  # Show first 3
                    logger.debug(f"    - {notification.subject or notification.text[:30]}")
                if notifications.count() > 3:
                    logger.debug(f"    ... and {notifications.count() - 3} more")

        if dry_run:
            logger.info(f"DRY RUN: Would have sent {total_emails_sent} digest emails")
            # Restore original log level
            if original_level is not None:
                logger.setLevel(original_level)
        else:
            logger.info(f"Successfully sent {total_emails_sent} digest emails")

    def get_notification_types_for_frequency(
        self,
        user: AbstractUser,
        wanted_frequency: type[NotificationFrequency],
        all_notification_types: list[type["NotificationType"]],
    ) -> list[type["NotificationType"]]:
        """
        Get all notification types that should use this frequency for the given user.
        This includes both explicit preferences and types that default to this frequency.
        Since notifications are only created for enabled channels, we don't need to check is_enabled.

        Args:
            user: The user to check preferences for
            wanted_frequency: The frequency to filter by (e.g. DailyFrequency, RealtimeFrequency)
            all_notification_types: List of all registered notification type classes

        Returns:
            List of notification type classes that use this frequency for this user
        """
        relevant_types: list[type["NotificationType"]] = []

        for notification_type in all_notification_types:
            user_frequency = notification_type.get_email_frequency(user)
            if user_frequency.key == wanted_frequency.key:
                relevant_types.append(notification_type)

        return relevant_types
