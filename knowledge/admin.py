from django.contrib import admin, messages

from .models import Chunk, Document
from .services.ingest import ingest_document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "business", "source_type", "status", "chunk_count", "flag_count", "created_at")
    list_filter = ("business", "source_type", "status")
    search_fields = ("title",)
    readonly_fields = ("status", "error", "flagged_lines", "created_at")
    actions = ["reprocess"]

    @admin.display(description="Chunks")
    def chunk_count(self, obj):
        return obj.chunks.count()

    @admin.display(description="Injection flags")
    def flag_count(self, obj):
        return len(obj.flagged_lines or [])

    @admin.action(description="Re-process selected documents (PDF and URL only)")
    def reprocess(self, request, queryset):
        done = 0
        for doc in queryset.exclude(source_type=Document.SourceType.TEXT):
            ingest_document(doc)
            done += 1
        self.message_user(request, f"Re-processed {done} document(s).", messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and obj.source_type != Document.SourceType.TEXT:
            ingest_document(obj)


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "index", "token_count")
    list_filter = ("business",)
    search_fields = ("content",)
    exclude = ("embedding",)
    readonly_fields = ("document", "business", "index", "content", "token_count")
