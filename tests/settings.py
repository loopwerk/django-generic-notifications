INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "generic_notifications",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

SECRET_KEY = "test_secret_key"
