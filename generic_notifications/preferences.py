from typing import Any, Dict, List

from django.contrib.auth.models import AbstractUser

from .models import NotificationFrequencyPreference, NotificationTypeChannelPreference
from .registry import registry


def get_notification_preferences(user: "AbstractUser") -> List[Dict[str, Any]]:
    """
    Get notification preferences data for a user.

    Returns a list of dictionaries, each containing:
    - notification_type: The NotificationType instance
    - channels: Dict of channel_key -> {channel, enabled, required}
    - notification_frequency: The current notification frequency key for this type

    This data structure can be used directly in templates to render
    notification preference forms.
    """
    notification_types = {nt.key: nt for nt in registry.get_all_types()}
    channels = {ch.key: ch for ch in registry.get_all_channels()}

    # Get user's channel preferences
    channel_preferences = {
        (pref.notification_type, pref.channel): pref.enabled
        for pref in NotificationTypeChannelPreference.objects.filter(user=user)
    }

    # Get user's notification frequency preferences
    notification_frequencies = dict(
        NotificationFrequencyPreference.objects.filter(user=user).values_list("notification_type", "frequency")
    )

    # Build settings data structure
    settings_data = []
    for notification_type in notification_types.values():
        type_key = notification_type.key
        type_data: Dict[str, Any] = {
            "notification_type": notification_type,
            "channels": {},
            "notification_frequency": notification_frequencies.get(type_key, notification_type.default_frequency.key),
        }

        for channel in channels.values():
            channel_key = channel.key
            is_required = channel_key in [ch.key for ch in notification_type.required_channels]
            is_forbidden = channel_key in [ch.key for ch in notification_type.forbidden_channels]

            # Determine if channel is enabled using the same logic as get_enabled_channels
            if is_forbidden:
                is_enabled = False
            elif is_required:
                is_enabled = True
            elif (type_key, channel_key) in channel_preferences:
                # User has explicit preference
                is_enabled = channel_preferences[(type_key, channel_key)]
            else:
                # No user preference - use defaults
                if notification_type.default_channels is not None:
                    is_enabled = channel in notification_type.default_channels
                else:
                    is_enabled = channel.enabled_by_default

            type_data["channels"][channel_key] = {
                "channel": channel,
                "enabled": is_enabled,
                "required": is_required,
                "forbidden": is_forbidden,
            }

        settings_data.append(type_data)

    return settings_data


def save_notification_preferences(user: "AbstractUser", form_data: Dict[str, Any]) -> None:
    """
    Save notification preferences from form data.

    Expected form_data format:
    - For channels: "{notification_type_key}__{channel_key}" -> "on" (if enabled)
    - For notification frequencies: "{notification_type_key}__frequency" -> frequency_key

    This function stores explicit preferences for both enabled and disabled channels.
    """
    # Clear existing preferences to rebuild from form data
    NotificationTypeChannelPreference.objects.filter(user=user).delete()
    NotificationFrequencyPreference.objects.filter(user=user).delete()

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

            # Check if this channel is required or forbidden (cannot be changed)
            if channel_key in [ch.key for ch in notification_type.required_channels]:
                continue
            if channel_key in [ch.key for ch in notification_type.forbidden_channels]:
                continue

            # Determine what the default would be for this channel
            if notification_type.default_channels is not None:
                default_enabled = channel in notification_type.default_channels
            else:
                default_enabled = channel.enabled_by_default

            # Check if form value differs from default
            form_enabled = form_key in form_data
            if form_enabled != default_enabled:
                # Store explicit preference since it differs from default
                if form_enabled:
                    notification_type.enable_channel(user=user, channel=channel)
                else:
                    notification_type.disable_channel(user=user, channel=channel)

        # Handle notification frequency preference
        frequency_key = f"{type_key}__frequency"
        if frequency_key in form_data:
            frequency_value = form_data[frequency_key]
            if frequency_value in frequencies:
                frequency_obj = frequencies[frequency_value]
                # Only save if different from default
                if frequency_value != notification_type.default_frequency.key:
                    notification_type.set_frequency(user=user, frequency=frequency_obj)
