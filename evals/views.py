from rest_framework import serializers, viewsets

from core.permissions import IsBusinessStaff, business_for

from .models import EvalResult, EvalRun


class EvalResultSerializer(serializers.ModelSerializer):
    question = serializers.CharField(source="question.question")
    expected_outcome = serializers.CharField(source="question.expected_outcome")

    class Meta:
        model = EvalResult
        fields = [
            "question", "expected_outcome", "outcome", "reason", "confidence", "cited_document",
            "cited_section", "routing_correct", "citation_correct", "keywords_found", "correct", "note", "answer",
        ]


class EvalRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalRun
        fields = [
            "id", "label", "config", "total", "accuracy", "routing_accuracy", "citation_accuracy",
            "handoff_rate", "unsafe_answers", "missed_answers", "created_at",
        ]


class EvalRunDetailSerializer(EvalRunSerializer):
    results = EvalResultSerializer(many=True, read_only=True)

    class Meta(EvalRunSerializer.Meta):
        fields = EvalRunSerializer.Meta.fields + ["results"]


class EvalRunViewSet(viewsets.ReadOnlyModelViewSet):
    """Eval history, newest first. Runs are created with `manage.py run_evals`."""

    permission_classes = [IsBusinessStaff]

    def get_serializer_class(self):
        return EvalRunSerializer if self.action == "list" else EvalRunDetailSerializer

    def get_queryset(self):
        qs = EvalRun.objects.filter(business=business_for(self.request))
        if self.action == "retrieve":
            qs = qs.prefetch_related("results__question")
        return qs
