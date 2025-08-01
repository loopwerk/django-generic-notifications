from django.urls import path

from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("notifications/", views.NotificationsView.as_view(), name="notifications"),
    path("notifications/archive/", views.NotificationsArchiveView.as_view(), name="notifications-archive"),
    path("notifications/settings/", views.NotificationSettingsView.as_view(), name="notification-settings"),
]
