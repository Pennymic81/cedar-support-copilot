from django.core.management.base import BaseCommand, CommandError

from core.models import Business
from knowledge.services.ingest import search


class Command(BaseCommand):
    help = 'Search the knowledge base from the terminal, e.g. manage.py ask "How long does a transfer to Spain take?"'

    def add_arguments(self, parser):
        parser.add_argument("query")
        parser.add_argument("--business", default="Cedar Pay")
        parser.add_argument("-k", type=int, default=3)

    def handle(self, *args, **opts):
        try:
            business = Business.objects.get(name=opts["business"])
        except Business.DoesNotExist as exc:
            raise CommandError(f"No business named {opts['business']!r}. Run seed_demo first.") from exc
        for chunk in search(business, opts["query"], opts["k"]):
            preview = " ".join(chunk.content.split())[:160]
            self.stdout.write(f"{chunk.score:.2f}  [{chunk.document.title} #{chunk.index}]  {preview}")
