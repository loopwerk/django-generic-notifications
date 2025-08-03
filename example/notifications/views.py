from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.generic import View
from generic_notifications import send_notification
from generic_notifications.preferences import get_notification_preferences, save_notification_preferences
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
        settings_data = get_notification_preferences(request.user)
        channels = {ch.key: ch for ch in registry.get_all_channels()}
        frequencies = {freq.key: freq for freq in registry.get_all_frequencies()}

        context = {
            "settings_data": settings_data,
            "channels": channels,
            "frequencies": frequencies,
        }
        return TemplateResponse(request, "settings.html", context=context)

    def post(self, request):
        save_notification_preferences(request.user, request.POST)
        return redirect("notification-settings")
