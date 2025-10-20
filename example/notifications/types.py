from generic_notifications.channels import EmailChannel, WebsiteChannel
from generic_notifications.types import NotificationType, register


@register
class CommentNotificationType(NotificationType):
    key = "comment_notification"
    name = "Comments"
    description = "You received a comment"
    default_channels = [WebsiteChannel]


@register
class WebsiteOnlyNotificationType(NotificationType):
    key = "website_only_notification"
    name = "Website only"
    description = "Just a test notification"
    forbidden_channels = [EmailChannel]
