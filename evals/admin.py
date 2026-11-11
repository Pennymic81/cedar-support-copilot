from django.contrib import admin

from .models import EvalQuestion, EvalResult, EvalRun


@admin.register(EvalQuestion)
class EvalQuestionAdmin(admin.ModelAdmin):
    list_display = ("question", "expected_outcome", "expected_reason", "expected_section")
    list_filter = ("business", "expected_outcome", "expected_reason")


class EvalResultInline(admin.TabularInline):
    model = EvalResult
    extra = 0


@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    list_display = ("label", "accuracy", "routing_accuracy", "citation_accuracy", "unsafe_answers", "created_at")
    list_filter = ("business",)
    inlines = [EvalResultInline]
