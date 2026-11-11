from django.core.management.base import BaseCommand, CommandError

from core.models import Business
from evals.services.runner import DEFAULT_FIXTURE, load_questions


class Command(BaseCommand):
    help = "Load eval questions from a JSON file (default: the Cedar Pay set), replacing existing ones."

    def add_arguments(self, parser):
        parser.add_argument("--business", default="Cedar Pay")
        parser.add_argument("--file", default=str(DEFAULT_FIXTURE))
        parser.add_argument("--append", action="store_true", help="Add to the existing questions instead")
        parser.add_argument("--if-empty", action="store_true", help="Do nothing if questions already exist")
        parser.add_argument("--if-changed", action="store_true", help="Reload only if the file's questions differ")

    def handle(self, *args, **opts):
        business = Business.objects.filter(name=opts["business"]).first()
        if business is None:
            raise CommandError(f"No business named {opts['business']!r}. Run seed_demo first.")
        if opts["if_empty"] and business.eval_questions.exists():
            self.stdout.write("Eval questions already loaded; skipping.")
            return
        if opts["if_changed"]:
            import json
            from pathlib import Path

            wanted = sorted(r["question"] for r in json.loads(Path(opts["file"]).read_text(encoding="utf-8")))
            current = sorted(business.eval_questions.values_list("question", flat=True))
            if wanted == current:
                self.stdout.write("Eval questions unchanged; skipping.")
                return
        n = load_questions(business, opts["file"], replace=not opts["append"])
        self.stdout.write(self.style.SUCCESS(f"Loaded {n} eval questions for {business.name}."))
