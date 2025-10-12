# Migrate from v1 to v2

Version 2.0.0 of django-generic-notifications has [a lot of improvements](https://github.com/loopwerk/django-generic-notifications/releases/tag/2.0.0), and some breaking changes in order to better support non-email digest channels. Most of these breaking changes will only affect you if you've written custom channels or frequencies. If you only added custom notification types, then most changes won't affect you.

## Renamed classes and methods

- Renamed `NotificationChannel` -> `BaseChannel`
- Renamed `NotificationFrequency` -> `BaseFrequency`
- Renamed `EmailFrequency` model to `NotificationFrequency` model
- Renamed `NotificationType.default_email_frequency` -> `NotificationType.default_frequency`
- Renamed `NotificationType.set_email_frequency` -> `NotificationType.set_frequency`
- Renamed `NotificationType.get_email_frequency` -> `NotificationType.get_frequency`
- Renamed `NotificationType.reset_email_frequency_to_default` -> `NotificationType.reset_frequency_to_default`
- Renamed `EmailChannel.send_email_now` -> `EmailChannel.send_now`
- Renamed `EmailChannel.send_digest_emails` -> `EmailChannel.send_digest`

This should be a simple matter of find-and-replace.

## Renamed send_digest_emails command

The `send_digest_emails` management command was renamed `send_notification_digests`. This means you'll need to update your cronjob or however else you started the digest command.

## BaseChannel changes

The `process` method moved from individual channel implementations to the `BaseChannel` class, which now calls either the `send_now` or `send_digest` method. This means that if you wrote a custom `BaseChannel` subclass, that you most likely can remove the `process` method and move the logic to the `send_now` and/or `send_digest` methods. Check the provided `WebsiteChannel` and `EmailChannel` for details.

## User preference changes

The `get_notification_preferences` function now returns `notification_frequency` instead of `email_frequency`. If you make use of `get_notification_preferences` to build a preference UI, you'll most likely need to check your usage and do this rename.
