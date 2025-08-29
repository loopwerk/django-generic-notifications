# Django Generic Notifications

A flexible, multi-channel notification system for Django applications with built-in support for email digests, user preferences, and extensible delivery channels.

## Features

- **Multi-channel delivery**: Send notifications through multiple channels (website, email, and custom channels)
- **Flexible email frequencies**: Support for real-time and digest emails (daily, or custom schedules)
- **Notification grouping**: Prevent repeated notifications by grouping notifications based on your own custom logic
- **User preferences**: Fine-grained control over notification types and delivery channels
- **Extensible architecture**: Easy to add custom notification types, channels, and frequencies
- **Generic relations**: Link notifications to any Django model
- **Template support**: Customizable email templates for each notification type
- **Developer friendly**: Simple API for sending notifications with automatic channel routing
- **Full type hints**: Complete type annotations for better IDE support and type checking

## Installation

All instruction in this document use [uv](https://github.com/astral-sh/uv), but of course pip or Poetry will also work just fine.

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

### 3. Set up email digest sending

Create a cron job to send daily digests:

```bash
# Send daily digests at 9 AM
0 9 * * * cd /path/to/project && uv run ./manage.py send_digest_emails --frequency daily
```

## User Preferences

By default every user gets notifications of all registered types delivered to every registered channel, but users can opt-out of receiving notification types, per channel.

All notification types default to daily digest, except for `SystemMessage` which defaults to real-time. Users can choose  different frequency per notification type.

This project doesn't come with a UI (view + template) for managing user preferences, but an example is provided in the [example app](#example-app).

### Using the preference helpers

The library does provide helper functions to simplify building preference management UIs:

```python
from generic_notifications.preferences import (
    get_notification_preferences,
    save_notification_preferences
)

# Get preferences for display in a form
# Returns a list of dicts with notification types, channels, and current settings
preferences = get_notification_preferences(user)

# Save preferences from form data
# Form field format: {notification_type_key}__{channel_key} and {notification_type_key}__frequency
save_notification_preferences(user, request.POST)
```

### Manual preference management

You can also manage preferences directly:

```python
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency
from generic_notifications.channels import EmailChannel
from generic_notifications.frequencies import RealtimeFrequency
from myapp.notifications import CommentNotification

# Disable email channel for comment notifications
CommentNotification.disable_channel(user=user, channel=EmailChannel)

# Change to realtime digest for a notification type
CommentNotification.set_email_frequency(user=user, frequency=RealtimeFrequency)
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

When you add custom email frequencies you’ll have to run `send_digest_emails` for them as well. For example, if you created that weekly digest:

```bash
# Send weekly digest every Monday at 9 AM
0 9 * * 1 cd /path/to/project && uv run ./manage.py send_digest_emails --frequency weekly
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

## Admin Integration

While the library doesn't register admin classes by default, the [example app](#example-app) includes [admin configuration](https://github.com/loopwerk/django-generic-notifications/tree/main/example/notifications/admin.py) that you can copy into your project for debugging and monitoring purposes.

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
from generic_notifications.channels import WebsiteChannel
from generic_notifications.models import Notification
from generic_notifications.lib import get_unread_count, get_notifications, mark_notifications_as_read

# Get unread count for a user
unread_count = get_unread_count(user=user, channel=WebsiteChannel)

# Get unread notifications for a user
unread_notifications = get_notifications(user=user, channel=WebsiteChannel, unread_only=True)

# Get notifications by channel
website_notifications = Notification.objects.for_channel(WebsiteChannel)

# Mark as read
notification = website_notifications.first()
notification.mark_as_read()

# Mark all as read
mark_notifications_as_read(user=user)
```

### Notification Grouping

Prevent notification spam by grouping similar notifications together. Instead of creating multiple "You received a comment" notifications, you can update an existing notification to say "You received 3 comments".

```python
@register
class CommentNotification(NotificationType):
    key = "comment"
    name = "Comment Notifications"
    description = "When someone comments on your posts"

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
            return False  # Don't create new notification

        # First notification of this type, so it should be saved
        return True

    def get_text(self, notification):
        count = notification.metadata.get("count", 1)
        actor_name = notification.actor.get_full_name()

        if count == 1:
            return f"{actor_name} commented on your post"
        else:
            return f"{actor_name} left {count} comments on your post"
```

The `should_save` method is called before saving each notification. Return `False` to prevent creating a new notification and instead update an existing one. This gives you complete control over grouping logic - you might group by time windows, actors, targets, or any other criteria.

## Performance Considerations

### Accessing `notification.target`

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

The problem is `target.article`, which cannot be prefetched and thus causes another query for every notification. This is why it’s better to store the subject, text and url in the notification itself, rather than relying on `target` dynamically.

### Non-blocking email sending

The email channel (EmailChannel) will send real-time emails using Django’s built-in `send_mail` method. This is a blocking function call, meaning that while a connection with the SMTP server is made and the email is sent off, the process that’s sending the notification has to wait. This is not ideal, but easily solved by using something like [django-mailer](https://github.com/pinax/django-mailer/), which provides a queueing backend for `send_mail`. This means that sending email is no longer a blocking action.

## Example app

An example app is provided, which shows how to create a custom notification type, how to send a notification, it has a nice looking notification center with unread notifications as well as an archive of all read notifications, plus a settings view where you can manage notification preferences.

```bash
cd example
uv run ./manage.py migrate
uv run ./manage.py runserver
```

Then open http://127.0.0.1:8000/.

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/loopwerk/django-generic-notifications.git
cd django-generic-notifications
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
