"""Ingestion: source -> text -> guard -> chunks -> embeddings -> database."""
from __future__ import annotations

from django.db import transaction
from pgvector.django import CosineDistance

from knowledge.models import Chunk, Document

from . import chunking, extract, guard
from .embeddings import EmbeddingError, get_embedder


def read_source(document: Document, text: str | None = None) -> str:
    if document.source_type == Document.SourceType.TEXT:
        if text is None:
            raise extract.ExtractionError("No text was provided.")
        return extract.normalize_whitespace(text)
    if document.source_type == Document.SourceType.PDF:
        if not document.file:
            raise extract.ExtractionError("No PDF file attached.")
        with document.file.open("rb") as fh:
            return extract.extract_pdf(fh.read())
    if document.source_type == Document.SourceType.URL:
        return extract.fetch_url(document.source_url)
    raise extract.ExtractionError(f"Unsupported source type: {document.source_type}")


def ingest_document(document: Document, text: str | None = None) -> Document:
    """Process a document synchronously. Sets status to ready or failed; never raises."""
    try:
        raw = read_source(document, text)
        scanned = guard.scan(raw)
        pieces = chunking.chunk_text(scanned.clean_text)
        if not pieces:
            raise extract.ExtractionError("No text left to index after cleaning.")
        # The title gives each chunk context ("Fees and transfer times" + a paragraph about Spain).
        vectors = get_embedder().embed([f"{document.title}\n\n{p.content}" for p in pieces])

        with transaction.atomic():
            document.chunks.all().delete()
            Chunk.objects.bulk_create(
                Chunk(
                    document=document,
                    business=document.business,
                    index=p.index,
                    content=p.content,
                    token_count=p.token_count,
                    embedding=v,
                )
                for p, v in zip(pieces, vectors)
            )
            document.status = Document.Status.READY
            document.error = ""
            document.flagged_lines = scanned.flagged_lines
            document.save(update_fields=["status", "error", "flagged_lines"])
    except (extract.ExtractionError, EmbeddingError) as exc:
        document.status = Document.Status.FAILED
        document.error = str(exc)
        document.save(update_fields=["status", "error"])
    return document


def search(business, query: str, k: int = 5):
    """Return the ``k`` chunks closest to ``query``, each annotated with ``score`` (0..1, higher is closer)."""
    [vector] = get_embedder().embed([query])
    results = list(
        Chunk.objects.filter(business=business, document__status=Document.Status.READY)
        .select_related("document")
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance")[:k]
    )
    for chunk in results:
        chunk.score = max(0.0, 1.0 - chunk.distance)
    return results
