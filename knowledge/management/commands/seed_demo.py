from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import Business, StaffProfile
from knowledge.models import Document
from knowledge.services.ingest import ingest_document

SAMPLE_DIR = Path(settings.BASE_DIR) / "sample_docs"


class Command(BaseCommand):
    help = "Create the Cedar Pay demo business, a staff login, and ingest the sample policy docs."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="agent")
        parser.add_argument("--password", help="Password for the demo staff login (skip to not create one)")

    def handle(self, *args, **opts):
        business, _ = Business.objects.get_or_create(name="Cedar Pay")
        self.stdout.write(f"Business: {business.name} (widget key {business.widget_key})")

        if opts["password"]:
            User = get_user_model()
            user, created = User.objects.get_or_create(username=opts["username"])
            user.set_password(opts["password"])
            user.is_staff = True
            user.save()
            StaffProfile.objects.update_or_create(
                user=user, defaults={"business": business, "role": StaffProfile.Role.ADMIN}
            )
            self.stdout.write(f"Staff login: {user.username} ({'created' if created else 'updated'})")

        for path in sorted(SAMPLE_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip()
            Document.objects.filter(business=business, title=title).delete()
            doc = Document.objects.create(business=business, title=title, source_type=Document.SourceType.TEXT)
            ingest_document(doc, text=text)
            self.stdout.write(f"  {doc.status:<6} {title} ({doc.chunks.count()} chunks)")

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
