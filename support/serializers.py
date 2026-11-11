from rest_framework import serializers

from knowledge.services.llm_helpers import section_title

from .models import Message


class ChatRequestSerializer(serializers.Serializer):
    widget_key = serializers.CharField(max_length=64)
    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    conversation_token = serializers.CharField(max_length=64, required=False)
    customer_ref = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CitationSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField(source="id")
    document_id = serializers.IntegerField(source="document.id")
    document_title = serializers.CharField(source="document.title")
    section = serializers.SerializerMethodField()
    score = serializers.FloatField()

    def get_section(self, chunk):
        return section_title(chunk.content)


class MessageSerializer(serializers.ModelSerializer):
    citations = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "sender", "content", "confidence", "citations", "created_at"]

    def get_citations(self, msg):
        return [
            {
                "chunk_id": c.chunk_id,
                "document_title": c.chunk.document.title,
                "section": section_title(c.chunk.content),
                "score": c.score,
            }
            for c in msg.citations.select_related("chunk__document")
        ]
