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

## Channel Defaults

Control which channels are enabled by default for different notification types and channels.

### Per-Channel Defaults

Set whether a channel is enabled by default across all notification types:

```python
@register
class SMSChannel(BaseChannel):
    key = "sms"
    name = "SMS"
    enabled_by_default = False  # Opt-in only - users must explicitly enable
    supports_realtime = True

@register
class PushChannel(BaseChannel):
    key = "push"
    name = "Push Notifications"
    enabled_by_default = True  # Opt-out - enabled unless user disables
    supports_realtime = True
```

The default value for `enabled_by_default` is `True`, maintaining backward compatibility.

### Per-NotificationType Defaults

Override channel defaults for specific notification types:

```python
@register
class MarketingEmail(NotificationType):
    key = "marketing"
    name = "Marketing Updates"
    # Only enable email by default, disable website notifications
    default_channels = [EmailChannel]

@register
class UrgentAlert(NotificationType):
    key = "urgent_alert"
    name = "Urgent Alerts"
    # Enable all channels including normally opt-in ones
    default_channels = [EmailChannel, WebsiteChannel, SMSChannel, PushChannel]
```

When `default_channels` is specified, it overrides the global `enabled_by_default` settings. If `default_channels` is `None` (the default), the system uses each channel's `enabled_by_default` setting.

### Priority Order

The system determines enabled channels in this priority order:

1. **Forbidden channels** - Always disabled (cannot be overridden)
2. **Required channels** - Always enabled (cannot be disabled)
3. **User preferences** - Explicit user enable/disable choices
4. **NotificationType.default_channels** - Per-type defaults (if specified)
5. **BaseChannel.enabled_by_default** - Global channel defaults

### Examples

```python
# Example: Marketing emails are opt-in only
@register
class MarketingEmail(NotificationType):
    key = "marketing"
    name = "Marketing Emails"
    default_channels = []  # No channels enabled by default

# Example: Critical alerts use all available channels
@register
class SecurityBreach(NotificationType):
    key = "security_breach"
    name = "Security Breach Alert"
    default_channels = [EmailChannel, SMSChannel, PushChannel]
    required_channels = [EmailChannel]  # Email cannot be disabled

# Example: Social notifications only on website by default
@register
class SocialNotification(NotificationType):
    key = "social"
    name = "Social Updates"
    default_channels = [WebsiteChannel]  # Only website, not email
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

## Forbidden Channels

Prevent certain channels from being used for specific notification types:

```python
from generic_notifications.channels import SMSChannel, WebsiteChannel

@register
class InternalAuditLog(NotificationType):
    key = "audit_log"
    name = "Internal Audit Log"
    description = "Internal system audit events"
    forbidden_channels = [SMSChannel]  # Never send audit logs via SMS
    default_channels = [WebsiteChannel]  # Only show in web interface

@register
class PrivacySensitiveNotification(NotificationType):
    key = "privacy_sensitive"
    name = "Privacy Sensitive Alert"
    description = "Contains sensitive personal information"
    forbidden_channels = [WebsiteChannel]  # Don't show in UI where others might see
    required_channels = [EmailChannel]  # Must go to private email
```

Forbidden channels take highest priority - they cannot be enabled even if specified in `default_channels`, `required_channels`, or user preferences.

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
