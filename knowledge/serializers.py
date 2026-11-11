from django.conf import settings
from rest_framework import serializers

from .models import Chunk, Document


class DocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.IntegerField(read_only=True)
    text = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = Document
        fields = [
            "id", "title", "source_type", "source_url", "file", "text",
            "status", "error", "flagged_lines", "chunk_count", "created_at",
        ]
        read_only_fields = ["status", "error", "flagged_lines", "chunk_count", "created_at"]

    def validate_file(self, value):
        if value and value.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"Files must be {settings.MAX_UPLOAD_MB} MB or smaller.")
        if value and not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        return value

    def validate(self, attrs):
        kind = attrs.get("source_type")
        needed = {
            Document.SourceType.PDF: ("file", "Upload a PDF file."),
            Document.SourceType.URL: ("source_url", "Give the page's URL."),
            Document.SourceType.TEXT: ("text", "Paste the text."),
        }
        field, msg = needed[kind]
        if not attrs.get(field):
            raise serializers.ValidationError({field: msg})
        return attrs


class SearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000)
    k = serializers.IntegerField(min_value=1, max_value=20, default=5)


class SearchResultSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title")
    score = serializers.FloatField()

    class Meta:
        model = Chunk
        fields = ["id", "document", "document_title", "index", "content", "score"]
