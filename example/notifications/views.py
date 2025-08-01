from typing import Any, Dict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.generic import View
from generic_notifications import send_notification
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency
from generic_notifications.registry import registry
from generic_notifications.utils import get_notifications, mark_notifications_as_read

from .types import CommentNotificationType


class HomeView(LoginRequiredMixin, View):
    def get(self, request):
        return TemplateResponse(request, "home.html")

    def post(self, request):
        # Send a test notification
        send_notification(
            recipient=request.user,
            notification_type=CommentNotificationType,
            subject="Test Notification",
            text="You received a new comment!",
        )

        return redirect("home")


class NotificationsView(LoginRequiredMixin, View):
    def get(self, request):
        notifications = get_notifications(user=request.user, unread_only=True)
        context = {
            "notifications": notifications,
            "archive": False,
        }
        return TemplateResponse(request, "notifications.html", context=context)

    def post(self, request):
        id = request.POST.get("id")
        if id:
            notifications = get_notifications(user=request.user)
            notification = notifications.get(id=id)
            notification.mark_as_read()
        else:
            mark_notifications_as_read(user=request.user)

        return redirect("notifications")


class NotificationsArchiveView(LoginRequiredMixin, View):
    def get(self, request):
        notifications = get_notifications(user=request.user, unread_only=False).filter(read__isnull=False)
        context = {
            "notifications": notifications,
            "archive": True,
        }
        return TemplateResponse(request, "notifications.html", context=context)

    def post(self, request):
        id = request.POST.get("id")
        if id:
            notifications = get_notifications(user=request.user)
            notification = notifications.get(id=id)
            notification.mark_as_unread()

        return redirect("notifications-archive")


class NotificationSettingsView(LoginRequiredMixin, View):
    def get(self, request):
        # Get all registered notification types, channels, and frequencies
        notification_types = {nt.key: nt for nt in registry.get_all_types()}
        channels = {ch.key: ch for ch in registry.get_all_channels()}
        frequencies = {freq.key: freq for freq in registry.get_all_frequencies()}

        # Get user's current disabled channels (opt-out system)
        disabled_channels = set(
            DisabledNotificationTypeChannel.objects.filter(user=request.user).values_list(
                "notification_type", "channel"
            )
        )

        # Get user's email frequency preferences
        email_frequencies = dict(
            EmailFrequency.objects.filter(user=request.user).values_list("notification_type", "frequency")
        )

        # Build settings data structure for template
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

        context = {
            "settings_data": settings_data,
            "channels": channels,
            "frequencies": frequencies,
        }
        return TemplateResponse(request, "settings.html", context=context)

    def post(self, request):
        # Clear existing preferences to rebuild from form data
        DisabledNotificationTypeChannel.objects.filter(user=request.user).delete()
        EmailFrequency.objects.filter(user=request.user).delete()

        notification_types = {nt.key: nt for nt in registry.get_all_types()}
        channels = {ch.key: ch for ch in registry.get_all_channels()}
        frequencies = {freq.key: freq for freq in registry.get_all_frequencies()}

        # Process form data
        for notification_type in notification_types.values():
            type_key = notification_type.key

            # Handle channel preferences
            for channel in channels.values():
                channel_key = channel.key
                form_key = f"{type_key}_{channel_key}"

                # Check if this channel is required (cannot be disabled)
                if channel_key in [ch.key for ch in notification_type.required_channels]:
                    continue

                # If checkbox not checked, create disabled entry
                if form_key not in request.POST:
                    DisabledNotificationTypeChannel.objects.create(
                        user=request.user, notification_type=type_key, channel=channel_key
                    )

            # Handle email frequency preference
            if "email" in [ch.key for ch in channels.values()]:
                frequency_key = f"{type_key}_frequency"
                if frequency_key in request.POST:
                    frequency_value = request.POST[frequency_key]
                    if frequency_value in frequencies:
                        # Only save if different from default
                        if frequency_value != notification_type.default_email_frequency.key:
                            EmailFrequency.objects.create(
                                user=request.user, notification_type=type_key, frequency=frequency_value
                            )

        return redirect("notification-settings")
