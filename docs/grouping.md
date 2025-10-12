## Notification Grouping

Prevent notification spam by grouping similar notifications together. Instead of creating multiple "You received a comment" notifications, you can update an existing notification to say "You received 3 comments".

```python
@register
class CommentNotification(NotificationType):
    key = "comment"
    name = "Comment Notifications"
    description = "When someone comments on your posts"

    @classmethod
    def should_save(cls, notification):
        # Look for existing unread notification with same actor and target
        existing = Notification.objects.filter(
            recipient=notification.recipient,
            notification_type=notification.notification_type,
            actor=notification.actor,
            content_type_id=notification.content_type_id,
            object_id=notification.object_id,
            read__isnull=True,
        ).first()

        if existing:
            # Update count in metadata
            count = existing.metadata.get("count", 1)
            existing.metadata["count"] = count + 1
            existing.save()
            return False  # Don't create new notification

        # First notification of this type, so it should be saved
        return True

    def get_text(self, notification):
        count = notification.metadata.get("count", 1)
        actor_name = notification.actor.get_full_name()

        if count == 1:
            return f"{actor_name} commented on your post"
        else:
            return f"{actor_name} left {count} comments on your post"
```

The `should_save` method is called before saving each notification. Return `False` to prevent creating a new notification and instead update an existing one. This gives you complete control over grouping logic - you might group by time windows, actors, targets, or any other criteria.
