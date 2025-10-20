## User Preferences

By default, users receive notifications based on the channel defaults configured for each notification type and channel (see [customizing.md](https://github.com/loopwerk/django-generic-notifications/tree/main/docs/customizing.md)). Users can then customize their preferences by explicitly enabling or disabling specific channels for each notification type.

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

# Change to realtime frequency for a notification type
CommentNotification.set_frequency(user=user, frequency=RealtimeFrequency)
```