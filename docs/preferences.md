## User Preferences

By default, users receive notifications based on the channel defaults configured for each notification type and channel. Users can then customize their preferences by explicitly enabling or disabling specific channels for each notification type.

The system supports both:

- **Channel preferences**: Enable/disable specific channels per notification type
- **Frequency preferences**: Choose between realtime delivery and digest delivery per notification type

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
from generic_notifications.models import NotificationTypeChannelPreference, NotificationFrequencyPreference
from generic_notifications.channels import EmailChannel
from generic_notifications.frequencies import RealtimeFrequency
from myapp.notifications import CommentNotification

# Disable email channel for comment notifications
CommentNotification.disable_channel(user=user, channel=EmailChannel)

# Enable email channel for comment notifications
CommentNotification.enable_channel(user=user, channel=EmailChannel)

# Check which channels are enabled for a user
enabled_channels = CommentNotification.get_enabled_channels(user)

# Set frequency preference directly in the database
NotificationFrequencyPreference.objects.update_or_create(
    user=user,
    notification_type=CommentNotification.key,
    defaults={'frequency': RealtimeFrequency.key}
)
```

### How defaults work

The system determines which channels are enabled using this priority order:

1. **Forbidden channels** - Always disabled (defined in `NotificationType.forbidden_channels`)
2. **Required channels** - Always enabled (defined in `NotificationType.required_channels`)
3. **User preferences** - Explicit user choices stored in `NotificationTypeChannelPreference`
4. **NotificationType defaults** - Per-type defaults (defined in `NotificationType.default_channels`)
5. **Channel defaults** - Global defaults (defined in `BaseChannel.enabled_by_default`)

This allows for flexible configuration where notification types can have different default behaviors while still allowing user customization.
