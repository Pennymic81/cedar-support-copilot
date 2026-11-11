from django.conf import settings
from django.db import migrations, models


def mark_existing(apps, schema_editor):
    # Everything indexed before this migration used the offline hashing embedder.
    Document = apps.get_model("knowledge", "Document")
    Document.objects.filter(status="ready").update(
        embedding_signature=f"local-hash:{settings.EMBEDDING_DIMENSIONS}"
    )


class Migration(migrations.Migration):
    dependencies = [("knowledge", "0002_document_flagged_lines")]

    operations = [
        migrations.AddField(
            model_name="document",
            name="embedding_signature",
            field=models.CharField(
                blank=True, help_text="Which embedding model produced this document's vectors", max_length=200
            ),
        ),
        migrations.RunPython(mark_existing, migrations.RunPython.noop),
    ]
