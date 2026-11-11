from django.core.management.base import BaseCommand, CommandError

from core.models import Business
from evals.models import EvalRun
from evals.services.runner import run


def pct(x):
    return "  –  " if x is None else f"{x * 100:5.1f}%"


class Command(BaseCommand):
    help = (
        "Run the eval set through the chat pipeline and score it.\n"
        "  run_evals --label baseline\n"
        "  run_evals --label strict --threshold 0.3\n"
        "  run_evals --sweep 0.1,0.15,0.2,0.25,0.3   (compare thresholds, nothing saved)"
    )

    def add_arguments(self, parser):
        parser.add_argument("--business", default="Cedar Pay")
        parser.add_argument("--label", default="run")
        parser.add_argument("--threshold", type=float, help="Override the confidence threshold for this run")
        parser.add_argument("--sweep", help="Comma-separated thresholds to compare (results not saved)")
        parser.add_argument("--quiet", action="store_true", help="Only print the summary")

    def handle(self, *args, **opts):
        business = Business.objects.filter(name=opts["business"]).first()
        if business is None:
            raise CommandError(f"No business named {opts['business']!r}. Run seed_demo first.")

        try:
            if opts["sweep"]:
                return self._sweep(business, [float(t) for t in opts["sweep"].split(",")])
            previous = business.eval_runs.first()
            result = run(business, opts["label"], threshold=opts["threshold"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not opts["quiet"]:
            self._failures(result)
        self._summary(result, previous)

    def _failures(self, result):
        wrong = [(q, o, s) for q, o, s in result._rows if not s["correct"]]
        self.stdout.write(f"\n{len(wrong)} of {result.total} questions need attention:\n")
        for q, o, s in wrong:
            flag = self.style.ERROR("UNSAFE ") if s["note"].startswith("UNSAFE") else "       "
            self.stdout.write(f"{flag}{q.question}\n         → {s['note']}  (confidence {o.confidence})")

    def _summary(self, r: EvalRun, previous: EvalRun | None):
        def delta(field, higher_is_better=True):
            if previous is None or getattr(previous, field) is None or getattr(r, field) is None:
                return ""
            d = getattr(r, field) - getattr(previous, field)
            if abs(d) < 1e-9:
                return "  (no change)"
            good = (d > 0) == higher_is_better
            text = f"  ({'+' if d > 0 else ''}{d * 100:.1f} pts vs {previous.label})"
            return self.style.SUCCESS(text) if good else self.style.ERROR(text)

        self.stdout.write(f"\nRun “{r.label}”  ·  {r.total} questions  ·  config {r.config}")
        self.stdout.write(f"  Accuracy            {pct(r.accuracy)}{delta('accuracy')}")
        self.stdout.write(f"  Routing accuracy    {pct(r.routing_accuracy)}{delta('routing_accuracy')}")
        self.stdout.write(f"  Citation accuracy   {pct(r.citation_accuracy)}{delta('citation_accuracy')}")
        self.stdout.write(f"  Handoff rate        {pct(r.handoff_rate)}")
        unsafe = f"  Unsafe answers      {r.unsafe_answers}"
        self.stdout.write(self.style.ERROR(unsafe) if r.unsafe_answers else self.style.SUCCESS(unsafe))
        self.stdout.write(f"  Missed answers      {r.missed_answers}\n")

    def _sweep(self, business, thresholds):
        self.stdout.write("\nthreshold  accuracy  routing  citations  handoff  unsafe  missed")
        for t in thresholds:
            r = run(business, f"sweep-{t}", threshold=t, save=False)
            self.stdout.write(
                f"  {t:<8} {pct(r.accuracy)}   {pct(r.routing_accuracy)}  {pct(r.citation_accuracy)}"
                f"   {pct(r.handoff_rate)}   {r.unsafe_answers:>3}    {r.missed_answers:>3}"
            )
        self.stdout.write("\nPick the lowest threshold with 0 unsafe answers, then trade off missed answers.\n")
