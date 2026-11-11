from django.core.management.base import BaseCommand, CommandError

from core.models import Business
from evals.services.runner import DEFAULT_FIXTURE, load_questions


class Command(BaseCommand):
    help = "Load eval questions from a JSON file (default: the Cedar Pay set), replacing existing ones."

    def add_arguments(self, parser):
        parser.add_argument("--business", default="Cedar Pay")
        parser.add_argument("--file", default=str(DEFAULT_FIXTURE))
        parser.add_argument("--append", action="store_true", help="Add to the existing questions instead")

    def handle(self, *args, **opts):
        business = Business.objects.filter(name=opts["business"]).first()
        if business is None:
            raise CommandError(f"No business named {opts['business']!r}. Run seed_demo first.")
        n = load_questions(business, opts["file"], replace=not opts["append"])
        self.stdout.write(self.style.SUCCESS(f"Loaded {n} eval questions for {business.name}."))
