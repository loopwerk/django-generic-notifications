# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development

```bash
# Install dependencies (using uv)
uv sync

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_models.py

# Run tests with verbose output
uv run pytest -v

# Type checking
uv run .

# Linting and formatting
uv run ruff check .
uv run ruff format .
```

## Architecture Overview

This is a Django package for handling generic notifications across multiple channels (email, website, etc.) with configurable delivery frequencies.

### Core Components

1. **Registry Pattern** (`registry.py`): Central registry that manages notification types, channels, and frequencies. All components must be registered here to be available.

2. **Notification Types** (`types.py`): Define different kinds of notifications (e.g., SystemMessage). Each type specifies:

   - Default email frequency (realtime vs digest)
   - Required channels that cannot be disabled
   - Dynamic subject/text generation methods
   - Custom channels can be added by subclassing `NotificationType`

3. **Channels** (`channels.py`): Delivery mechanisms for notifications:

   - `WebsiteChannel`: Stores in database for UI display
   - `EmailChannel`: Sends via email (supports realtime + digest)
   - Custom channels can be added by subclassing `NotificationChannel`

4. **Frequencies** (`frequencies.py`): Email delivery timing options:

   - `RealtimeFrequency`: Send immediately
   - `DailyFrequency`: Bundle into daily digest
   - Custom frequencies can be added by subclassing `NotificationFrequency`

5. **Models** (`models.py`):
   - `Notification`: Core notification instance with recipient, type, channels, content
   - `DisabledNotificationTypeChannel`: Opt-out preferences (presence = disabled)
   - `EmailFrequency`: Per-user email frequency preferences

### Key Design Decisions

- **Opt-out model**: Notifications are enabled by default; users disable specific type/channel combinations
- **Channel determination at creation**: When a notification is created, enabled channels are determined and stored in the `channels` JSONField
- **Digest processing**: Email digests are handled by a management command that queries unsent, unread notifications
- **Generic relations**: Notifications can reference any Django model via ContentType/GenericForeignKey
- **PostgreSQL optimization**: Uses GIN indexes for efficient JSONField queries

### Common Workflows

1. **Sending a notification**:

   ```python
   from generic_notifications import send_notification
   from myapp.notifications import CommentNotification

   send_notification(
       recipient=user,
       notification_type=CommentNotification,
       actor=commenter,
       target=post,
       subject="New comment",
       text="Someone commented on your post"
   )
   ```

2. **Registering a new notification type**:

   ```python
   from generic_notifications.types import NotificationType, register

   @register
   class CommentNotification(NotificationType):
       key = "comment"
       name = "Comments"
       description = "When someone comments on your content"
       default_email_frequency = DailyFrequency
   ```

3. **User preferences**: Managed through `DisabledNotificationTypeChannel` and `EmailFrequency` models
