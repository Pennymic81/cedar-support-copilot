from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.permissions import IsBusinessStaff, business_for

from .models import Document
from .serializers import DocumentSerializer, SearchRequestSerializer, SearchResultSerializer
from .services.ingest import ingest_document, search


class DocumentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Upload, list and remove the documents the copilot answers from.

    POST with source_type=pdf (multipart, `file`), url (`source_url`) or text (`text`).
    Documents are processed straight away; the response shows status ready or failed.
    """

    serializer_class = DocumentSerializer
    permission_classes = [IsBusinessStaff]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return (
            Document.objects.filter(business=business_for(self.request))
            .annotate(chunk_count=Count("chunks"))
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data.pop("text", None)
        document = serializer.save(business=business_for(request))
        ingest_document(document, text=text)
        document = self.get_queryset().get(pk=document.pk)
        code = status.HTTP_201_CREATED if document.status == Document.Status.READY else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(self.get_serializer(document).data, status=code)

    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        """Re-run ingestion, e.g. after changing the embedding provider (not for pasted text)."""
        document = self.get_object()
        if document.source_type == Document.SourceType.TEXT:
            return Response({"detail": "Pasted text can't be reprocessed; upload it again."}, status=400)
        ingest_document(document)
        return Response(self.get_serializer(self.get_queryset().get(pk=document.pk)).data)


@api_view(["POST"])
@permission_classes([IsBusinessStaff])
def search_view(request):
    """Semantic search over the business's documents (used by the chat in Day 3, handy for debugging now)."""
    params = SearchRequestSerializer(data=request.data)
    params.is_valid(raise_exception=True)
    results = search(business_for(request), params.validated_data["query"], params.validated_data["k"])
    return Response({"results": SearchResultSerializer(results, many=True).data})
