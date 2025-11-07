# Django Generic Notifications

A flexible, multi-channel notification system for Django applications with built-in support for email digests, user preferences, and extensible delivery channels.

## Features

- **Multi-channel delivery**: Send notifications through multiple channels (website, email, and custom channels)
- **Flexible delivery frequencies**: Support for real-time and digest delivery (daily, or custom schedules)
- **Notification grouping**: Prevent repeated notifications by grouping notifications based on your own custom logic
- **User preferences**: Fine-grained control over notification types and delivery channels
- **Extensible architecture**: Easy to add custom notification types, channels, and frequencies
- **Generic relations**: Link notifications to any Django model
- **Template support**: Customizable email templates for each notification type
- **Developer friendly**: Simple API for sending notifications with automatic channel routing
- **Full type hints**: Complete type annotations for better IDE support and type checking

## Requirements

- Python >= 3.10
- Django >= 4.2.0
- `django.contrib.contenttypes` must be in `INSTALLED_APPS`

## Installation

All instruction in this document use [uv](https://github.com/astral-sh/uv), but of course pip or Poetry will also work just fine.

```bash
uv add django-generic-notifications
```

Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "django.contrib.contenttypes",  # Required dependency
    "generic_notifications",
    ...
]
```

Run migrations:

```bash
uv run ./manage.py migrate generic_notifications
```

## Settings

### `NOTIFICATION_BASE_URL`

Configure the base URL for generating absolute URLs in email notifications:

```python
# With protocol (recommended)
NOTIFICATION_BASE_URL = "https://www.example.com"
NOTIFICATION_BASE_URL = "http://localhost:8000"

# Without protocol (auto-detects based on DEBUG setting)
NOTIFICATION_BASE_URL = "www.example.com"
```

**Protocol handling**: If you omit the protocol, it's automatically added:

- `https://` in production (`DEBUG = False`)
- `http://` in development (`DEBUG = True`)

**Fallback order** if `NOTIFICATION_BASE_URL` is not set:

1. `BASE_URL` setting
2. `SITE_URL` setting
3. Django Sites framework (if `django.contrib.sites` is installed)
4. URLs remain relative if no base URL is found (not ideal in emails!)

## Quick Start

### 1. Define a notification type

```python
# myapp/notifications.py
from generic_notifications.types import NotificationType, register

@register
class CommentNotification(NotificationType):
    key = "comment"
    name = "Comment Notifications"
    description = "When someone comments on your posts"
```

### 2. Send a notification

```python
from generic_notifications import send_notification
from myapp.notifications import CommentNotification

# Send a notification (only `recipient` and `notification_type` are required)
notification = send_notification(
    recipient=post.author,
    notification_type=CommentNotification,
    actor=comment.user,
    target=post,
    subject=f"{comment.user.get_full_name()} commented on your post",
    text=f"{comment.user.get_full_name()} left a comment: {comment.text[:100]}",
    url=f"/posts/{post.id}#comment-{comment.id}",
)
```

### 3. Working with notifications

```python
from generic_notifications.channels import WebsiteChannel
from generic_notifications.models import Notification
from generic_notifications.lib import get_unread_count, get_notifications, mark_notifications_as_read

# Get unread count for a user
unread_count = get_unread_count(user=user, channel=WebsiteChannel)

# Get unread notifications for a user
unread_notifications = get_notifications(user=user, channel=WebsiteChannel, unread_only=True)

# Get notifications by channel
website_notifications = Notification.objects.prefetch().for_channel(WebsiteChannel)

# Mark as read
notification = website_notifications.first()
notification.mark_as_read()

# Mark all as read
mark_notifications_as_read(user=user)
```

### 4. Set up email digest sending

Create a cron job to send daily digests:

```bash
# Send daily digests at 9 AM
0 9 * * * cd /path/to/project && uv run ./manage.py send_notification_digests --frequency daily
```

If you already have a way to run scheduled jobs in your Django app and don't want to start a management command via a cron job, you can call the `send_notification_digests` function directly:

```python
from generic_notifications.digest import send_notification_digests
from generic_notifications.frequencies import DailyFrequency

send_notification_digests(frequency=DailyFrequency, dry_run=False)
```

## Example App

An example app is provided, which shows how to create a custom notification type, how to send a notification, it has a nice looking notification center with unread notifications as well as an archive of all read notifications, plus a settings view where you can manage notification preferences.

```bash
cd example
uv run ./manage.py migrate
uv run ./manage.py runserver
```

Then open http://127.0.0.1:8000/.

## Admin Integration

While the library doesn't register admin classes by default, the example app includes [admin configuration](https://github.com/loopwerk/django-generic-notifications/tree/main/example/notifications/admin.py) that you can copy into your project for debugging and monitoring purposes.

## Further Documentation

- [Migrate to a newer version of this library](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/migrate.md)
- [Customization: custom channels, frequencies, and email templates](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/customizing.md)
- [Performance considerations and tips](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/performance.md)
- [Notification grouping: prevent notification spam by grouping similar notifications together](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/grouping.md)
- [Supporting multilingual notifications](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/multilingual.md)
- [User preferences: how to manage user preferences](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/preferences.md)
- [Development: workflows for working on this library](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/development.md)

## Sponsored By

A huge thanks goes to https://dskrpt.de/ for sponsoring development of django-generic-notifications.

## License

MIT License - see LICENSE file for details.
