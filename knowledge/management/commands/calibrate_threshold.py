from django.core.management.base import BaseCommand, CommandError

from core.models import Business
from knowledge.services.calibrate import calibrate
from knowledge.services.embeddings import EmbeddingError, LocalHashEmbedder, get_embedder


class Command(BaseCommand):
    help = (
        "Set the business's confidence threshold from retrieval scores on the eval set.\n"
        "Skipped for the offline embedder, whose threshold was tuned by hand (0.21)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--business", default="Cedar Pay")
        parser.add_argument("--dry-run", action="store_true", help="Show the result without saving it")
        parser.add_argument("--force", action="store_true", help="Calibrate even for the offline embedder")

    def handle(self, *args, **opts):
        business = Business.objects.filter(name=opts["business"]).first()
        if business is None:
            raise CommandError(f"No business named {opts['business']!r}.")
        if isinstance(get_embedder(), LocalHashEmbedder) and not opts["force"]:
            self.stdout.write(f"Offline embedder: keeping threshold {business.effective_threshold}.")
            return
        try:
            result = calibrate(business)
        except (ValueError, EmbeddingError) as exc:
            # Never fail a deploy over this; the provider default still applies.
            self.stderr.write(f"Calibration skipped: {exc}")
            return
        fmt = lambda xs: ", ".join(f"{x:.3f}" for x in xs)
        self.stdout.write(f"Should answer : {fmt(result.answer_scores)}")
        self.stdout.write(f"Off-topic     : {fmt(result.off_topic_scores)}")
        self.stdout.write(f"Threshold {result.threshold}: {result.correct}/{result.total} routed correctly by score.")
        if not opts["dry_run"]:
            business.confidence_threshold = result.threshold
            business.save(update_fields=["confidence_threshold"])
            self.stdout.write(self.style.SUCCESS("Saved."))
