## Multilingual Notifications

For applications that support multiple languages, you have two main approaches to handle translatable notification content.

### Approach 1: store parameters per language in metadata

Store translated parameters for each language in the `metadata` field and use Django's translation system in `get_text()`:

```python
from django.utils.translation import gettext as _, get_language

@register
class CommentNotificationType(NotificationType):
    key = "comment"
    name = "Comments"
    description = "When someone comments on your content"

    def get_text(self, notification):
        current_lang = get_language()
        # Get parameters for current language, fallback to English
        lang_params = notification.metadata.get(current_lang, notification.metadata.get("en", {}))

        return _("%(commenter_name)s commented on %(page_title)s") % lang_params

# When creating the notification
from django.conf import settings
from django.utils.translation import activate, get_language

def create_multilingual_notification(recipient, commenter, page):
    current_lang = get_language()
    multilingual_metadata = {}

    # Store parameters for each language
    for lang_code, _ in settings.LANGUAGES:
        activate(lang_code)
        multilingual_metadata[lang_code] = {
            "commenter_name": commenter.get_full_name(),
            "page_title": page.get_title(),  # Assumes this returns translated title
        }

    activate(current_lang)  # Restore original language

    send_notification(
        recipient=recipient,
        notification_type=CommentNotificationType,
        actor=commenter,
        target=page,
        metadata=multilingual_metadata
    )
```

**Pros**: Best query performance  
**Cons**: Parameters are "frozen" when notification is created, more database storage needed

### Approach 2: dynamic translation via target

Use the `target` relationship to access current translated data:

```python
@register
class CommentNotificationType(NotificationType):
    key = "comment"
    name = "Comments"
    description = "When someone comments on your content"

    def get_text(self, notification):
        from django.utils.translation import gettext as _

        # Access current language data from the target
        if notification.target:
            return _("%(commenter)s commented on %(page_title)s") % {
                "commenter": notification.actor.get_full_name(),
                "page_title": notification.target.get_title()  # Assumes this returns translated title
            }
        return self.description

# Usage is simple - just send the notification
send_notification(
    recipient=page.author,
    notification_type=CommentNotificationType,
    actor=commenter,
    target=page
)
```

**Pros**: Always current data, minimal storage, simpler code  
**Cons**: Requires proper prefetching for [performance](https://github.com/loopwerk/django-generic-notifications/blob/main/docs/performance.md)

### Performance considerations

| Approach   | Storage Overhead | Query Performance       | Translation Freshness |
| ---------- | ---------------- | ----------------------- | --------------------- |
| Approach 1 | Moderate         | Excellent               | Frozen when created   |
| Approach 2 | None             | Good (with prefetching) | Always current        |

- Use **approach 1** if you have performance-critical displays and can accept that text is frozen when the notification is created
- Use **approach 2** if you need always-current data
