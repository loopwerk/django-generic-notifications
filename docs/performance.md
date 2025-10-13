## Performance Considerations

### Accessing `notification.target`

The `target` field is a GenericForeignKey that can point to any Django model instance. While convenient, accessing targets requires careful consideration for performance.

When using Django 5.0+, this library automatically includes `.prefetch_related("target")` when using the standard query methods. This efficiently fetches target objects, but only the _direct_ targets - accessing relationships _through_ the target will still cause additional queries.

_On Django 4.2, you'll need to manually deal with prefetching the `target` relationship._

Consider this problematic example that will cause N+1 queries:

```python
class Article(models.Model):
    title = models.CharField(max_length=255)
    text = models.TextField()


class Comment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment_text = models.TextField()


@register
class CommentNotificationType(NotificationType):
    key = "comment_notification"
    name = "Comments"
    description = "You received a comment"

    def get_text(self, notification):
        actor_name = notification.actor.full_name
        article = notification.target.article
        comment_text = notification.target.comment_text

        # This causes an extra query per notification!
        return f'{actor_name} commented on your article "{article.title}": "{comment_text}"'
```

When displaying a list of 10 notifications, this will execute:

- 1 query for the notifications
- 1 query for the target comments (Django 5.0+ only, automatically prefetched)
- 10 queries for the articles (N+1 problem!)

#### Solution 1: store data in the notification

The simplest approach is to store the needed data directly in the notification:

```python
send_notification(
    recipient=article.author,
    notification_type=CommentNotificationType,
    actor=commenter,
    target=comment,
    subject=f"New comment on {article.title}",
    text=f'{commenter.full_name} commented on your article "{article.title}": "{comment.comment_text}"',
    url=article.get_absolute_url()
)
```

However, this only works if you don’t need to dynamically generate the text - for example to make sure the text is always up to date, or to deal with internationalization.

#### Solution 2: prefetch deeper relationships

If you must access relationships through the target, you can prefetch them:

```python
# On Django 5.0+ the library already prefetches targets,
# but you need to add deeper relationships yourself
notifications = get_notifications(user).prefetch_related(
    "target__article"  # This prevents the N+1 problem
)
```

**Warning**: This approach has serious limitations:

- You need to know the target's type and relationships in advance
- Only works when ALL notifications in the queryset have the same target model type
- It will raise `AttributeError` with heterogeneous targets (different model types) - if even one notification has a different target type that lacks the specified relationship, the entire query will fail
- Each additional relationship level requires explicit prefetching

#### For best performance

1. If possible, store all display data directly in the notification (subject, text, url)
2. If you need dynamic text, prefer accessing only direct fields on the target
3. Otherwise, make sure you prefetch the right relationships

### Non-blocking email sending

The email channel (EmailChannel) will send real-time emails using Django’s built-in `send_mail` method. This is a blocking function call, meaning that while a connection with the SMTP server is made and the email is sent off, the process that’s sending the notification has to wait. This is not ideal, but easily solved by using something like [django-mailer](https://github.com/pinax/django-mailer/), which provides a queueing backend for `send_mail`. This means that sending email is no longer a blocking action.
