from django.db import models

from core.models import Business


class Outcome(models.TextChoices):
    ANSWER = "answer", "AI answers"
    HANDOFF = "handoff", "Handed to a person"


class EvalQuestion(models.Model):
    """A test question and what the copilot should do with it."""

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="eval_questions")
    question = models.TextField()
    expected_outcome = models.CharField(max_length=10, choices=Outcome.choices)
    expected_reason = models.CharField(
        max_length=20, blank=True, help_text="For handoffs: sensitive, low_confidence or customer_requested"
    )
    expected_document_title = models.CharField(max_length=300, blank=True, help_text="For answers: the source document")
    expected_section = models.CharField(max_length=300, blank=True, help_text="For answers: the source section")
    expected_keywords = models.JSONField(
        default=list, blank=True, help_text="For answers: words or figures the answer must contain"
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.question[:60]


class EvalRun(models.Model):
    """One run of the whole test set, e.g. 'baseline' or 'threshold-0.25'."""

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="eval_runs")
    label = models.CharField(max_length=100)
    config = models.JSONField(default=dict, blank=True, help_text="Providers and threshold used")
    total = models.PositiveIntegerField(default=0)
    accuracy = models.FloatField(null=True, blank=True, help_text="Share of questions fully correct")
    routing_accuracy = models.FloatField(null=True, blank=True, help_text="Answered vs handed off correctly")
    citation_accuracy = models.FloatField(null=True, blank=True, help_text="Answers citing the right section")
    handoff_rate = models.FloatField(null=True, blank=True)
    unsafe_answers = models.PositiveIntegerField(default=0, help_text="Should have gone to a person, AI answered")
    missed_answers = models.PositiveIntegerField(default=0, help_text="AI could have answered, handed off instead")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.label


class EvalResult(models.Model):
    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="results")
    question = models.ForeignKey(EvalQuestion, on_delete=models.CASCADE, related_name="results")
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    reason = models.CharField(max_length=20, blank=True)
    answer = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    cited_document = models.CharField(max_length=300, blank=True)
    cited_section = models.CharField(max_length=300, blank=True)
    routing_correct = models.BooleanField()
    citation_correct = models.BooleanField(null=True, help_text="Answers only")
    keywords_found = models.BooleanField(null=True, help_text="Answers only")
    correct = models.BooleanField()
    note = models.CharField(max_length=300, blank=True, help_text="Why it was marked wrong")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "question"], name="unique_result_per_run"),
        ]
