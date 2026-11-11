from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

from core.models import Business


class Document(models.Model):
    """A source the copilot may answer from: an uploaded PDF, a web page or pasted text."""

    class SourceType(models.TextChoices):
        PDF = "pdf", "PDF"
        URL = "url", "Web page"
        TEXT = "text", "Text"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=300)
    source_type = models.CharField(max_length=10, choices=SourceType.choices)
    source_url = models.URLField(blank=True)
    file = models.FileField(upload_to="documents/", blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    error = models.TextField(blank=True)
    flagged_lines = models.JSONField(
        default=list, blank=True, help_text="Lines removed by the prompt-injection guard"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title


class Chunk(models.Model):
    """A piece of a document plus its embedding, used for retrieval."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField(help_text="Position of the chunk within its document")
    content = models.TextField()
    token_count = models.PositiveIntegerField(null=True, blank=True)
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "index"], name="unique_chunk_position"),
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document} #{self.index}"
