from django.db import models

from core.models import Business
from knowledge.models import Document


class EvalQuestion(models.Model):
    """A test question with the answer we expect."""

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="eval_questions")
    question = models.TextField()
    expected_answer = models.TextField()
    expected_document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL)
    should_handoff = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.question[:60]


class EvalRun(models.Model):
    """One run of the whole test set, e.g. 'baseline' or 'reranking-v1'."""

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="eval_runs")
    label = models.CharField(max_length=100)
    accuracy = models.FloatField(null=True, blank=True)
    citation_accuracy = models.FloatField(null=True, blank=True)
    handoff_rate = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.label


class EvalResult(models.Model):
    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="results")
    question = models.ForeignKey(EvalQuestion, on_delete=models.CASCADE, related_name="results")
    answer = models.TextField(blank=True)
    correct = models.BooleanField(null=True)
    citation_correct = models.BooleanField(null=True)
    handed_off = models.BooleanField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "question"], name="unique_result_per_run"),
        ]
