## User Preferences

By default every user gets notifications of all registered types delivered to every registered channel, but users can opt-out of receiving notification types, per channel.

All notification types default to daily digest, except for `SystemMessage` which defaults to real-time. Users can choose different frequency per notification type.

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
from generic_notifications.models import DisabledNotificationTypeChannel, NotificationFrequency
from generic_notifications.channels import EmailChannel
from generic_notifications.frequencies import RealtimeFrequency
from myapp.notifications import CommentNotification

# Disable email channel for comment notifications
CommentNotification.disable_channel(user=user, channel=EmailChannel)

# Change to realtime digest for a notification type
CommentNotification.set_frequency(user=user, frequency=RealtimeFrequency)
```
