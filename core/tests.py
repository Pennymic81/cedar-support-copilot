from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Business, StaffProfile
from knowledge.models import Chunk, Document
from support.models import Conversation, Message, Ticket


class HealthTests(TestCase):
    def test_health_reports_pgvector(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIsNotNone(response.json()["pgvector"])


class ModelTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Cedar Pay")

    def test_business_gets_unique_widget_key(self):
        other = Business.objects.create(name="Other")
        self.assertTrue(self.business.widget_key.startswith("wk_"))
        self.assertNotEqual(self.business.widget_key, other.widget_key)

    def test_staff_profile_links_user_to_business(self):
        user = get_user_model().objects.create_user("agent", password="test-pass-123")
        StaffProfile.objects.create(user=user, business=self.business)
        self.assertEqual(user.staff.business, self.business)

    def test_nearest_chunk_is_found_by_cosine_distance(self):
        from django.conf import settings
        from pgvector.django import CosineDistance

        dims = settings.EMBEDDING_DIMENSIONS
        doc = Document.objects.create(business=self.business, title="Limits", source_type="text")
        near = [1.0] + [0.0] * (dims - 1)
        far = [0.0, 1.0] + [0.0] * (dims - 2)
        Chunk.objects.create(document=doc, business=self.business, index=0, content="near", embedding=near)
        Chunk.objects.create(document=doc, business=self.business, index=1, content="far", embedding=far)

        best = (
            Chunk.objects.filter(business=self.business)
            .annotate(distance=CosineDistance("embedding", near))
            .order_by("distance")
            .first()
        )
        self.assertEqual(best.content, "near")

    def test_handoff_ticket_for_conversation(self):
        convo = Conversation.objects.create(business=self.business, status=Conversation.Status.ESCALATED)
        Message.objects.create(conversation=convo, sender="customer", content="Where is my money?")
        ticket = Ticket.objects.create(
            conversation=convo, business=self.business, reason=Ticket.Reason.SENSITIVE
        )
        self.assertEqual(convo.ticket, ticket)
        self.assertEqual(ticket.status, Ticket.Status.PENDING)
