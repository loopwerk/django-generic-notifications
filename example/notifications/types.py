from generic_notifications.types import NotificationType, register


@register
class CommentNotificationType(NotificationType):
    key = "comment_notification"
    name = "Comments"
    description = "You received a comment"
