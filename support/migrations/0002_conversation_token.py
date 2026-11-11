import secrets

from django.db import migrations, models

import support.models


def fill_tokens(apps, schema_editor):
    Conversation = apps.get_model("support", "Conversation")
    for convo in Conversation.objects.filter(token__isnull=True):
        convo.token = secrets.token_urlsafe(24)
        convo.save(update_fields=["token"])


class Migration(migrations.Migration):

    dependencies = [
        ("support", "0001_initial"),
    ]

    operations = [
        # 1. add the column without a unique constraint
        migrations.AddField(
            model_name="conversation",
            name="token",
            field=models.CharField(max_length=64, null=True),
        ),
        # 2. give every existing conversation its own token
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        # 3. make it required and unique
        migrations.AlterField(
            model_name="conversation",
            name="token",
            field=models.CharField(
                default=support.models.new_conversation_token,
                help_text="Secret the widget uses to continue or read this chat",
                max_length=64,
                unique=True,
            ),
        ),
    ]
