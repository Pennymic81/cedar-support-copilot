from rest_framework import serializers

from knowledge.services.llm_helpers import section_title

from .models import Message, Ticket


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


class TicketListSerializer(serializers.ModelSerializer):
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    assigned_to = serializers.CharField(source="assigned_to.username", default=None, read_only=True)
    last_customer_message = serializers.SerializerMethodField()
    customer_ref = serializers.CharField(source="conversation.customer_ref", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "status", "reason", "reason_label", "reason_detail", "summary",
            "customer_ref", "last_customer_message", "assigned_to", "created_at", "closed_at",
        ]

    def get_last_customer_message(self, ticket):
        msg = ticket.conversation.messages.filter(sender="customer").last()
        return msg.content if msg else ""


class DraftSourceSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField(source="id")
    document_title = serializers.CharField(source="document.title")
    section = serializers.SerializerMethodField()
    content = serializers.CharField()

    def get_section(self, chunk):
        return section_title(chunk.content)


class TicketDetailSerializer(TicketListSerializer):
    messages = MessageSerializer(source="conversation.messages", many=True, read_only=True)
    draft_sources = DraftSourceSerializer(many=True, read_only=True)

    class Meta(TicketListSerializer.Meta):
        fields = TicketListSerializer.Meta.fields + [
            "suggested_reply", "draft_grounded", "draft_sources", "draft_outcome", "messages",
        ]


class AgentReplySerializer(serializers.Serializer):
    content = serializers.CharField(max_length=4000, required=False, allow_blank=False)
    use_draft = serializers.BooleanField(default=False)
    close = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("content") and not attrs["use_draft"]:
            raise serializers.ValidationError("Send `content`, or `use_draft: true` to send the suggested reply.")
        return attrs
