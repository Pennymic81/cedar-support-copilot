from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Replace the Day 1 placeholder eval tables (never used) with the real eval schema."""

    dependencies = [
        ("core", "0002_optional_confidence_threshold"),
        ("evals", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="EvalResult"),
        migrations.DeleteModel(name="EvalRun"),
        migrations.DeleteModel(name="EvalQuestion"),
        migrations.CreateModel(
            name="EvalQuestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("question", models.TextField()),
                (
                    "expected_outcome",
                    models.CharField(
                        choices=[
                            ("answer", "AI answers"),
                            ("handoff", "Handed to a person"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "expected_reason",
                    models.CharField(
                        blank=True,
                        help_text="For handoffs: sensitive, low_confidence or customer_requested",
                        max_length=20,
                    ),
                ),
                (
                    "expected_document_title",
                    models.CharField(
                        blank=True,
                        help_text="For answers: the source document",
                        max_length=300,
                    ),
                ),
                (
                    "expected_section",
                    models.CharField(
                        blank=True,
                        help_text="For answers: the source section",
                        max_length=300,
                    ),
                ),
                (
                    "expected_keywords",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="For answers: words or figures the answer must contain",
                    ),
                ),
                ("note", models.CharField(blank=True, max_length=300)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eval_questions",
                        to="core.business",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="EvalRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("label", models.CharField(max_length=100)),
                (
                    "config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Providers and threshold used",
                    ),
                ),
                ("total", models.PositiveIntegerField(default=0)),
                (
                    "accuracy",
                    models.FloatField(
                        blank=True,
                        help_text="Share of questions fully correct",
                        null=True,
                    ),
                ),
                (
                    "routing_accuracy",
                    models.FloatField(
                        blank=True,
                        help_text="Answered vs handed off correctly",
                        null=True,
                    ),
                ),
                (
                    "citation_accuracy",
                    models.FloatField(
                        blank=True,
                        help_text="Answers citing the right section",
                        null=True,
                    ),
                ),
                ("handoff_rate", models.FloatField(blank=True, null=True)),
                (
                    "unsafe_answers",
                    models.PositiveIntegerField(
                        default=0, help_text="Should have gone to a person, AI answered"
                    ),
                ),
                (
                    "missed_answers",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="AI could have answered, handed off instead",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eval_runs",
                        to="core.business",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="EvalResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("answer", "AI answers"),
                            ("handoff", "Handed to a person"),
                        ],
                        max_length=10,
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=20)),
                ("answer", models.TextField(blank=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("cited_document", models.CharField(blank=True, max_length=300)),
                ("cited_section", models.CharField(blank=True, max_length=300)),
                ("routing_correct", models.BooleanField()),
                (
                    "citation_correct",
                    models.BooleanField(help_text="Answers only", null=True),
                ),
                (
                    "keywords_found",
                    models.BooleanField(help_text="Answers only", null=True),
                ),
                ("correct", models.BooleanField()),
                (
                    "note",
                    models.CharField(
                        blank=True, help_text="Why it was marked wrong", max_length=300
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="evals.evalquestion",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="evals.evalrun",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "question"), name="unique_result_per_run"
                    )
                ],
            },
        ),
    ]
