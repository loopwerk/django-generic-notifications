from typing import Any, Dict, List

from django.contrib.auth.models import AbstractUser

from .models import DisabledNotificationTypeChannel, EmailFrequency
from .registry import registry


def get_notification_preferences(user: "AbstractUser") -> List[Dict[str, Any]]:
    """
    Get notification preferences data for a user.

    Returns a list of dictionaries, each containing:
    - notification_type: The NotificationType instance
    - channels: Dict of channel_key -> {channel, enabled, required}
    - email_frequency: The current email frequency key for this type

    This data structure can be used directly in templates to render
    notification preference forms.
    """
    notification_types = {nt.key: nt for nt in registry.get_all_types()}
    channels = {ch.key: ch for ch in registry.get_all_channels()}

    # Get user's current disabled channels (opt-out system)
    disabled_channels = set(
        DisabledNotificationTypeChannel.objects.filter(user=user).values_list("notification_type", "channel")
    )

    # Get user's email frequency preferences
    email_frequencies = dict(EmailFrequency.objects.filter(user=user).values_list("notification_type", "frequency"))

    # Build settings data structure
    settings_data = []
    for notification_type in notification_types.values():
        type_key = notification_type.key
        type_data: Dict[str, Any] = {
            "notification_type": notification_type,
            "channels": {},
            "email_frequency": email_frequencies.get(type_key, notification_type.default_email_frequency.key),
        }

        for channel in channels.values():
            channel_key = channel.key
            is_disabled = (type_key, channel_key) in disabled_channels
            is_required = channel_key in [ch.key for ch in notification_type.required_channels]

            type_data["channels"][channel_key] = {
                "channel": channel,
                "enabled": is_required or not is_disabled,  # Required channels are always enabled
                "required": is_required,
            }

        settings_data.append(type_data)

    return settings_data


def save_notification_preferences(user: "AbstractUser", form_data: Dict[str, Any]) -> None:
    """
    Save notification preferences from form data.

    Expected form_data format:
    - For channels: "{notification_type_key}__{channel_key}" -> "on" (if enabled)
    - For email frequencies: "{notification_type_key}__frequency" -> frequency_key

    This function implements an opt-out model: channels are enabled by default
    and only disabled entries are stored in the database.
    """
    # Clear existing preferences to rebuild from form data
    DisabledNotificationTypeChannel.objects.filter(user=user).delete()
    EmailFrequency.objects.filter(user=user).delete()

    notification_types = {nt.key: nt for nt in registry.get_all_types()}
    channels = {ch.key: ch for ch in registry.get_all_channels()}
    frequencies = {freq.key: freq for freq in registry.get_all_frequencies()}

    # Process form data
    for notification_type in notification_types.values():
        type_key = notification_type.key

        # Handle channel preferences
        for channel in channels.values():
            channel_key = channel.key
            form_key = f"{type_key}__{channel_key}"

            # Check if this channel is required (cannot be disabled)
            if channel_key in [ch.key for ch in notification_type.required_channels]:
                continue

            # If checkbox not checked, create disabled entry
            if form_key not in form_data:
                notification_type.disable_channel(user=user, channel=channel)

        # Handle email frequency preference
        if "email" in [ch.key for ch in channels.values()]:
            frequency_key = f"{type_key}__frequency"
            if frequency_key in form_data:
                frequency_value = form_data[frequency_key]
                if frequency_value in frequencies:
                    frequency_obj = frequencies[frequency_value]
                    # Only save if different from default
                    if frequency_value != notification_type.default_email_frequency.key:
                        notification_type.set_email_frequency(user=user, frequency=frequency_obj)
