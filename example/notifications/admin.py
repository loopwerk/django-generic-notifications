from django.contrib import admin
from generic_notifications.models import DisabledNotificationTypeChannel, Notification, NotificationFrequency


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "notification_type", "added", "get_channels"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("channels")

    @admin.display(description="Channels")
    def get_channels(self, obj):
        channels = obj.channels.values_list("channel", flat=True)
        return ", ".join(channels) if channels else "-"


@admin.register(DisabledNotificationTypeChannel)
class DisabledNotificationTypeChannelAdmin(admin.ModelAdmin):
    list_display = ["user", "notification_type", "channel"]


@admin.register(NotificationFrequency)
class NotificationFrequencyAdmin(admin.ModelAdmin):
    list_display = ["user", "notification_type", "frequency"]
