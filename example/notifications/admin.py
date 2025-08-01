from django.contrib import admin
from generic_notifications.models import DisabledNotificationTypeChannel, EmailFrequency, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "notification_type", "added", "channels"]


@admin.register(DisabledNotificationTypeChannel)
class DisabledNotificationTypeChannelAdmin(admin.ModelAdmin):
    list_display = ["user", "notification_type", "channel"]


@admin.register(EmailFrequency)
class EmailFrequencyAdmin(admin.ModelAdmin):
    list_display = ["user", "notification_type", "frequency"]
