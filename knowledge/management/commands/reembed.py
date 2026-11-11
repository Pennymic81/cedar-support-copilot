from django.core.management.base import BaseCommand

from knowledge.models import Document
from knowledge.services.embeddings import EmbeddingError, get_embedder
from knowledge.services.ingest import reembed_document


class Command(BaseCommand):
    help = "Re-embed every ready document whose vectors came from a different embedding model."

    def handle(self, *args, **opts):
        embedder = get_embedder()
        stale = Document.objects.filter(status=Document.Status.READY).exclude(
            embedding_signature=embedder.signature
        )
        if not stale.exists():
            self.stdout.write(f"All documents already use {embedder.signature}.")
            return
        failed = 0
        for doc in stale:
            try:
                reembed_document(doc, embedder)
                self.stdout.write(f"  re-embedded  {doc.title}")
            except EmbeddingError as exc:
                failed += 1
                self.stderr.write(f"  FAILED       {doc.title}: {exc}")
        msg = f"Now using {embedder.signature}."
        self.stdout.write(self.style.WARNING(msg + f" {failed} failed.") if failed else self.style.SUCCESS(msg))
