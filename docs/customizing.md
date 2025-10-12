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
from generic_notifications.channels import EmailChannel

@register
class SecurityAlert(NotificationType):
    key = "security_alert"
    name = "Security Alerts"
    description = "Important security notifications"
    required_channels = [EmailChannel]  # Cannot be disabled
```

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

### Digest emails

- `notifications/email/digest/subject.txt`
- `notifications/email/digest/message.html`
- `notifications/email/digest/message.txt`
