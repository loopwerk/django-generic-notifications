from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

User = get_user_model()


class AutoLoginMiddleware:
    """Automatically logs in the default user for example app."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if isinstance(request.user, AnonymousUser):
            try:
                default_user = User.objects.get(username="demo")
                request.user = default_user
                request._cached_user = default_user
            except User.DoesNotExist:
                pass

        response = self.get_response(request)
        return response
