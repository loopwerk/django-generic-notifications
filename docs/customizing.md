## Custom Channels

Create custom delivery channels:

```python
from generic_notifications.channels import BaseChannel, register

@register
class SMSChannel(BaseChannel):
    key = "sms"
    name = "SMS"
    supports_realtime = True
    supports_digest = False

    def should_send(self, notification):
        return bool(getattr(notification.recipient, "phone_number", None))

    def send_now(self, notification):
        # Send SMS using your preferred service
        send_sms(
            to=notification.recipient.phone_number,
            message=notification.get_text()
        )
```

## Required Channels

Make certain channels mandatory for critical notifications:

```python
from generic_notifications.types import NotificationType
from generic_notifications.channels import EmailChannel

@register
class SecurityAlert(NotificationType):
    key = "security_alert"
    name = "Security Alerts"
    description = "Important security notifications"
    required_channels = [EmailChannel]  # Cannot be disabled
```

## Forbidden Channels

Prevent certain channels from being used for specific notification types:

```python
from generic_notifications.types import NotificationType
from generic_notifications.channels import SMSChannel

@register
class CommentReceivedNotification(NotificationType):
    key = "comment_received"
    name = "Comment received"
    description = "You received a comment"
    forbidden_channels = [SMSChannel]  # Never send via SMS
```

Forbidden channels take highest priority - they cannot be enabled even if specified in `default_channels`, `required_channels`, or user preferences.

## Defaults Channels

By default all channels are enabled for all users, and for all notifications types. Control which channels are enabled by default.

### Per-Channel Defaults

Disable a channel by default across all notification types:

```python
@register
class SMSChannel(BaseChannel):
    key = "sms"
    name = "SMS"
    supports_realtime = True
    supports_digest = False
    enabled_by_default = False  # Opt-in only - users must explicitly enable
```

### Per-NotificationType Defaults

By default all channels are enabled for every notification type. You can override channel defaults for specific notification types:

```python
@register
class MarketingEmail(NotificationType):
    key = "marketing"
    name = "Marketing Updates"
    # Only enable email by default
    # (users can still opt-in to enable other channels)
    default_channels = [EmailChannel]
```

### Priority Order

The system determines enabled channels in this priority order:

1. **Forbidden channels** - Always disabled (cannot be overridden)
2. **Required channels** - Always enabled (cannot be disabled)
3. **User preferences** - Explicit user enable/disable choices (see [preferences.md](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/preferences.md))
4. **NotificationType.default_channels** - Per-type defaults (if specified)
5. **BaseChannel.enabled_by_default** - Global channel defaults

## Custom Frequencies

Add custom email frequencies:

```python
from generic_notifications.frequencies import BaseFrequency, register

@register
class WeeklyFrequency(BaseFrequency):
    key = "weekly"
    name = "Weekly digest"
    is_realtime = False
    description = "Receive a weekly summary every Monday"
```

When you add custom email frequencies you'll have to run `send_notification_digests` for them as well. For example, if you created that weekly digest:

```bash
# Send weekly digest every Monday at 9 AM
0 9 * * 1 cd /path/to/project && uv run ./manage.py send_notification_digests --frequency weekly
```

## Email Templates

Customize email templates by creating these files in your templates directory:

### Real-time emails

- `notifications/email/realtime/{notification_type}_subject.txt`
- `notifications/email/realtime/{notification_type}.html`
- `notifications/email/realtime/{notification_type}.txt`

If notification-type specific templates are not found, the system will fall back to:

- `notifications/email/realtime/subject.txt`
- `notifications/email/realtime/body.html`
- `notifications/email/realtime/body.txt`

This allows you to create generic templates that work for all notification types while still having the flexibility to create specific templates for certain types.

### Digest emails

- `notifications/email/digest/subject.txt`
- `notifications/email/digest/message.html`
- `notifications/email/digest/message.txt`
