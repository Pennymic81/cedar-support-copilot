from django.contrib import admin

from .models import EvalQuestion, EvalResult, EvalRun


@admin.register(EvalQuestion)
class EvalQuestionAdmin(admin.ModelAdmin):
    list_display = ("question", "business", "should_handoff")
    list_filter = ("business", "should_handoff")


class EvalResultInline(admin.TabularInline):
    model = EvalResult
    extra = 0


@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    list_display = ("label", "business", "accuracy", "citation_accuracy", "handoff_rate", "created_at")
    list_filter = ("business",)
    inlines = [EvalResultInline]
