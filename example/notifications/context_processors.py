from generic_notifications.utils import get_unread_count


def notifications(request):
    return {"unread_notifications": get_unread_count(request.user)}
