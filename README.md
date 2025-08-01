# Django Generic Notifications

A flexible, multi-channel notification system for Django applications with built-in support for email digests, user preferences, and extensible delivery channels.

## Features

- **Multi-channel delivery**: Send notifications through multiple channels (website, email, and custom channels)
- **Flexible email frequencies**: Support for real-time and digest emails (daily, or custom schedules)
- **User preferences**: Fine-grained control over notification types and delivery channels
- **Extensible architecture**: Easy to add custom notification types, channels, and frequencies
- **Generic relations**: Link notifications to any Django model
- **Template support**: Customizable email templates for each notification type
- **Developer friendly**: Simple API for sending notifications with automatic channel routing
- **Full type hints**: Complete type annotations for better IDE support and type checking

## Installation

Install using [uv](https://github.com/astral-sh/uv):

```bash
uv add django-generic-notifications
```

Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "generic_notifications",
    ...
]
```

Run migrations:

```bash
uv run ./manage.py migrate generic_notifications
```

## Quick Start

### 1. Define a notification type

```python
# myapp/notifications.py
from generic_notifications.types import NotificationType, register
from generic_notifications.frequencies import DailyFrequency

@register
class CommentNotification(NotificationType):
    key = "comment"
    name = "Comment Notifications"
    description = "When someone comments on your posts"
    default_email_frequency = DailyFrequency

    def get_subject(self, notification):
        return f"{notification.actor.get_full_name()} commented on your post"

    def get_text(self, notification):
        return f"{notification.actor.get_full_name()} left a comment: {notification.metadata.get('preview', '')}"
```

### 2. Send a notification

```python
from generic_notifications import send_notification
from myapp.notifications import CommentNotification

# Send a notification
notification = send_notification(
    recipient=post.author,
    notification_type=CommentNotification,
    actor=comment.user,
    target=post,
    url=f"/posts/{post.id}#comment-{comment.id}",
    metadata={
        'preview': comment.text[:100]
    }
)
```

### 3. Set up email digest sending

Create a cron job to send daily digests:

```bash
# Send daily digests at 9 AM
0 9 * * * cd /path/to/project && uv run ./manage.py send_digest_emails --frequency daily
```

For weekly digests (e.g., Mondays at 9 AM):

```bash
0 9 * * 1 cd /path/to/project && uv run ./manage.py send_digest_emails --frequency weekly
```

## User Preferences

Users can control their notification preferences:

```python
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency

# Disable email channel for comment notifications
DisabledNotificationTypeChannel.objects.create(
    user=user,
    notification_type="comment",
    channel="email"
)

# Change to weekly digest for a notification type
EmailFrequency.objects.update_or_create(
    user=user,
    notification_type="comment",
    defaults={'frequency': 'weekly'}
)
```

## Custom Channels

Create custom delivery channels:

```python
from generic_notifications.channels import NotificationChannel, register

@register
class SMSChannel(NotificationChannel):
    key = "sms"
    name = "SMS"

    def process(self, notification):
        # Send SMS using your preferred service
        send_sms(
            to=notification.recipient.phone_number,
            message=notification.get_text()
        )
```

## Custom Frequencies

Add custom email frequencies:

```python
from generic_notifications.frequencies import NotificationFrequency, register

@register
class WeeklyFrequency(NotificationFrequency):
    key = "weekly"
    name = "Weekly digest"
    is_realtime = False
    description = "Receive a weekly summary every Monday"
```

## Email Templates

Customize email templates by creating these files in your templates directory:

### Real-time emails

- `notifications/email/realtime/{notification_type}_subject.txt`
- `notifications/email/realtime/{notification_type}.html`
- `notifications/email/realtime/{notification_type}.txt`

### Digest emails

- `notifications/email/digest/subject.txt`
- `notifications/email/digest/message.html`
- `notifications/email/digest/message.txt`

## Advanced Usage

### Required Channels

Make certain channels mandatory for critical notifications:

```python
from generic_notifications.channels import EmailChannel

@register
class SecurityAlert(NotificationType):
    key = "security_alert"
    name = "Security Alerts"
    description = "Important security notifications"
    required_channels = [EmailChannel]  # Cannot be disabled
```

### Querying Notifications

```python
from generic_notifications.models import Notification
from generic_notifications.lib import get_unread_count, get_notifications, mark_notifications_as_read

# Get unread count for a user
unread_count = get_unread_count(user=user, channel=WebsiteChannel)

# Get unread notifications for a user
unread_notifications = get_notifications(user=user, channel=WebsiteChannel, unread_only=True)

# Get notifications by channel
email_notifications = Notification.objects.for_channel(WebsiteChannel)

# Mark as read
notification.mark_as_read()

# Mark all as read
mark_notifications_as_read(user=user)
```

## Performance Considerations

While you can store any object into a notification's `target` field, it's usually not a great idea to use this field to dynamically create the notification's subject and text, as the `target` generic relationship can't be prefetched more than one level deep.

In other words, something like this will cause an N+1 query problem when you show a list of notifications in a table, for example:

```python
class Comment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment_text = models.TextField()


@register
class CommentNotificationType(NotificationType):
    key = "comment_notification"
    name = "Comments"
    description = "You received a comment"

    def get_text(self, notification):
          actor_name = notification.actor.full_name
          article = notification.target.article
          comment_text = notification.target.comment.comment_text
          return f'{actor_name} commented on your article "{article.title}": "{comment_text}"'

```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/loopwerk/django-generic-notifications.git
cd django-generic-notifications

# Install dependencies with uv
uv sync
```

### Testing

```bash
# Run all tests
uv run pytest
```

### Code Quality

```bash
# Type checking
uv run mypy .

# Linting
uv run ruff check .

# Formatting
uv run ruff format .
```

## License

MIT License - see LICENSE file for details.
