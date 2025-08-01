from django.contrib.auth import get_user_model
from django.db import migrations

User = get_user_model()


def create_default_user(apps, schema_editor):
    if not User.objects.filter(username="demo").exists():
        User.objects.create_user(
            username="demo",
            email="demo@example.com",
            password="demo",
            first_name="Demo",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )


def delete_default_user(apps, schema_editor):
    User.objects.filter(username="demo").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_default_user, delete_default_user),
    ]
