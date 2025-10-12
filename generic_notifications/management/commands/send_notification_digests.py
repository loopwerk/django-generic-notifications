import logging

from django.core.management.base import BaseCommand

from generic_notifications.digest import send_notification_digests
from generic_notifications.registry import registry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send notification digests to users who have opted for digest delivery"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without actually sending the digests",
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
            logger.info("DRY RUN - No notifications will be sent")

        try:
            # Get the frequency class from the registry
            frequency_cls = registry.get_frequency(target_frequency)
            if not frequency_cls:
                raise KeyError(f"Frequency '{target_frequency}' not found")

            total_digests_sent = send_notification_digests(frequency_cls, dry_run)

            if dry_run:
                logger.info(f"DRY RUN: Would have sent {total_digests_sent} digest notifications")
                # Restore original log level
                if original_level is not None:
                    logger.setLevel(original_level)
            else:
                logger.info(f"Successfully sent {total_digests_sent} digest notifications")

        except (KeyError, ValueError) as e:
            logger.error(str(e))
            return
