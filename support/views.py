from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.models import Business

from .models import Conversation
from .serializers import ChatRequestSerializer, CitationSerializer, MessageSerializer
from .services.chat import handle_customer_message


class ChatThrottle(ScopedRateThrottle):
    scope = "chat"


def _business_for_key(key):
    return Business.objects.filter(widget_key=key).first()


@api_view(["POST"])
@authentication_classes([])  # widget calls carry no cookies or user identity
@permission_classes([AllowAny])
@throttle_classes([ChatThrottle])
def chat(request):
    """Public endpoint the chat widget calls. Authenticated by the business's widget key.

    Body: {"widget_key": "...", "message": "...", "conversation_token": "..." (to continue a chat)}
    """
    req = ChatRequestSerializer(data=request.data)
    req.is_valid(raise_exception=True)
    data = req.validated_data

    business = _business_for_key(data["widget_key"])
    if business is None:
        return Response({"detail": "Unknown widget key."}, status=status.HTTP_403_FORBIDDEN)

    if data.get("conversation_token"):
        convo = Conversation.objects.filter(token=data["conversation_token"], business=business).first()
        if convo is None:
            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        convo = Conversation.objects.create(business=business, customer_ref=data.get("customer_ref", ""))

    result = handle_customer_message(convo, data["message"])
    return Response(
        {
            "conversation_token": convo.token,
            "status": convo.status,
            "reply": {
                "id": result.reply.id,
                "content": result.reply.content,
                "confidence": result.reply.confidence,
                "handed_off": result.handed_off,
                "citations": CitationSerializer(result.citations, many=True).data,
            },
        }
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ChatThrottle])
def conversation_history(request, token):
    """Messages so far, so the widget can restore a chat (and pick up agent replies)."""
    business = _business_for_key(request.query_params.get("widget_key", ""))
    convo = Conversation.objects.filter(token=token, business=business).first() if business else None
    if convo is None:
        return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "conversation_token": convo.token,
            "status": convo.status,
            "messages": MessageSerializer(convo.messages.all(), many=True).data,
        }
    )
