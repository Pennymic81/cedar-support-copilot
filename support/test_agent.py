import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Business, StaffProfile
from support.models import Conversation, Message, Ticket
from support.services import sensitive
from support.services.drafts import NO_POLICY_DRAFT


class SensitiveRuleTests(SimpleTestCase):
    def test_money_and_account_problems_are_caught(self):
        cases = {
            "I was charged $250 but the transfer failed. Where is my money?": "money_missing",
            "My transfer never arrived": "money_missing",
            "I got charged twice": "money_missing",
            "Someone used my card, I didn't make this payment": "fraud",
            "I want a refund": "refund_dispute",
            "My account is blocked": "account_access",
            "I lost my card": "account_access",
        }
        for text, expected in cases.items():
            self.assertEqual(sensitive.detect(text), expected, text)

    def test_general_questions_are_not_caught(self):
        for text in [
            "How long does a transfer to Spain take?",
            "What happens if a transfer fails?",
            "Can I cancel a transfer?",
            "Is my money safe with you?",
        ]:
            self.assertIsNone(sensitive.detect(text), text)


class HandoffTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=io.StringIO())
        cls.business = Business.objects.get(name="Cedar Pay")
        User = get_user_model()
        cls.agent = User.objects.create_user("agent1", password="test-pass-123")
        StaffProfile.objects.create(user=cls.agent, business=cls.business)
        cls.other_business = Business.objects.create(name="Other Co")
        cls.outsider = User.objects.create_user("outsider", password="test-pass-123")
        StaffProfile.objects.create(user=cls.outsider, business=cls.other_business)

    def setUp(self):
        self.widget = APIClient()
        self.agent_client = APIClient()
        self.agent_client.force_authenticate(self.agent)

    def customer_says(self, message, token=None):
        body = {"widget_key": self.business.widget_key, "message": message}
        if token:
            body["conversation_token"] = token
        return self.widget.post("/api/chat/", body, format="json").json()


class SensitiveHandoffTests(HandoffTestBase):
    def test_money_problem_skips_the_ai_answer_and_drafts_from_policy(self):
        resp = self.customer_says("I was charged $250 but the transfer failed. Where is my money?")
        self.assertTrue(resp["reply"]["handed_off"])
        self.assertIn("involves your money", resp["reply"]["content"])

        ticket = Ticket.objects.get()
        self.assertEqual(ticket.reason, Ticket.Reason.SENSITIVE)
        self.assertEqual(ticket.reason_detail, "money_missing")
        self.assertTrue(ticket.draft_grounded)
        self.assertIn("24 hours", ticket.suggested_reply)
        self.assertIn("transaction reference", ticket.suggested_reply)
        self.assertIn("Failed transfers and reversals", ticket.summary)
        self.assertEqual(ticket.draft_sources.get().document.title, "Failed transfers and reversals")

    def test_unknown_topic_gets_an_honest_placeholder_draft(self):
        self.customer_says("Do you offer car loans?")
        ticket = Ticket.objects.get()
        self.assertFalse(ticket.draft_grounded)
        self.assertEqual(ticket.suggested_reply, NO_POLICY_DRAFT)
        self.assertEqual(ticket.draft_sources.count(), 0)


class InboxTests(HandoffTestBase):
    def setUp(self):
        super().setUp()
        resp = self.customer_says("I was charged $250 but the transfer failed. Where is my money?")
        self.token = resp["conversation_token"]
        self.ticket = Ticket.objects.get()

    def test_list_and_detail(self):
        listing = self.agent_client.get("/api/tickets/", {"status": "pending"}).json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["reason_detail"], "money_missing")
        self.assertIn("Where is my money", listing[0]["last_customer_message"])

        detail = self.agent_client.get(f"/api/tickets/{self.ticket.id}/").json()
        self.assertEqual([m["sender"] for m in detail["messages"]], ["customer", "ai"])
        self.assertEqual(detail["draft_sources"][0]["section"], "What happens to your money")

    def test_other_businesses_and_anonymous_users_cannot_see_tickets(self):
        outsider = APIClient()
        outsider.force_authenticate(self.outsider)
        self.assertEqual(outsider.get("/api/tickets/").json(), [])
        self.assertEqual(outsider.get(f"/api/tickets/{self.ticket.id}/").status_code, 404)
        self.assertEqual(APIClient().get("/api/tickets/").status_code, 403)

    def test_assign_to_self_and_to_teammate(self):
        detail = self.agent_client.post(f"/api/tickets/{self.ticket.id}/assign/").json()
        self.assertEqual(detail["assigned_to"], "agent1")
        self.assertEqual(detail["status"], "in_progress")
        bad = self.agent_client.post(f"/api/tickets/{self.ticket.id}/assign/", {"user_id": self.outsider.id})
        self.assertEqual(bad.status_code, 400)

    def test_approve_draft_and_close_returns_chat_to_ai(self):
        detail = self.agent_client.post(
            f"/api/tickets/{self.ticket.id}/reply/", {"use_draft": True, "close": True}, format="json"
        ).json()
        self.assertEqual(detail["status"], "closed")
        self.assertEqual(detail["draft_outcome"], "approved")
        agent_msg = Message.objects.get(sender="agent")
        self.assertEqual(agent_msg.content, self.ticket.suggested_reply)
        self.assertEqual(agent_msg.author, self.agent)

        # the customer sees the agent's reply in their history
        history = self.widget.get(f"/api/chat/{self.token}/", {"widget_key": self.business.widget_key}).json()
        self.assertEqual(history["status"], "resolved")
        self.assertEqual(history["messages"][-1]["sender"], "agent")

        # and the next question is answered by the AI again
        resp = self.customer_says("How long does a transfer to Spain take?", token=self.token)
        self.assertFalse(resp["reply"]["handed_off"])
        self.assertEqual(Conversation.objects.get().status, "open")

    def test_edited_draft_is_recorded_as_edited(self):
        detail = self.agent_client.post(
            f"/api/tickets/{self.ticket.id}/reply/",
            {"use_draft": True, "content": "Hi! Your $250 will be back within 24 hours."},
            format="json",
        ).json()
        self.assertEqual(detail["draft_outcome"], "edited")
        self.assertEqual(detail["status"], "in_progress")

    def test_reply_needs_content_or_draft(self):
        resp = self.agent_client.post(f"/api/tickets/{self.ticket.id}/reply/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_cannot_send_placeholder_draft(self):
        self.customer_says("Do you offer car loans?")
        loan = Ticket.objects.exclude(pk=self.ticket.pk).get()
        resp = self.agent_client.post(f"/api/tickets/{loan.id}/reply/", {"use_draft": True}, format="json")
        self.assertEqual(resp.status_code, 400)
        written = self.agent_client.post(
            f"/api/tickets/{loan.id}/reply/", {"content": "We don't offer loans yet."}, format="json"
        ).json()
        self.assertEqual(written["draft_outcome"], "written")

    def test_closed_ticket_reopens_on_new_handoff(self):
        self.agent_client.post(f"/api/tickets/{self.ticket.id}/close/")
        self.customer_says("Actually my card is blocked now", token=self.token)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "pending")
        self.assertEqual(self.ticket.reason_detail, "account_access")
        self.assertIsNone(self.ticket.closed_at)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_closed_ticket_rejects_replies(self):
        self.agent_client.post(f"/api/tickets/{self.ticket.id}/close/")
        resp = self.agent_client.post(f"/api/tickets/{self.ticket.id}/reply/", {"content": "hi"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_redraft_after_customer_adds_details(self):
        Message.objects.create(conversation=self.ticket.conversation, sender="customer", content="It's been 3 days")
        detail = self.agent_client.post(f"/api/tickets/{self.ticket.id}/redraft/").json()
        self.assertIn("(2 messages)", detail["summary"])

    def test_filter_mine(self):
        self.assertEqual(self.agent_client.get("/api/tickets/", {"mine": "true"}).json(), [])
        self.agent_client.post(f"/api/tickets/{self.ticket.id}/assign/")
        self.assertEqual(len(self.agent_client.get("/api/tickets/", {"mine": "true"}).json()), 1)

    @override_settings(LLM_PROVIDER="openai", LLM_API_KEY="test-key")
    def test_model_draft_is_used_when_provider_is_configured(self):
        fake = mock.Mock()
        fake.raise_for_status.return_value = None
        fake.json.return_value = {
            "choices": [{"message": {"content": "SUMMARY: Customer's $250 transfer failed.\nREPLY: Sorry! It comes back within 24 hours [1]."}}]
        }
        with mock.patch("support.services.llm.requests.post", return_value=fake):
            detail = self.agent_client.post(f"/api/tickets/{self.ticket.id}/redraft/").json()
        self.assertEqual(detail["summary"], "Customer's $250 transfer failed.")
        self.assertEqual(detail["suggested_reply"], "Sorry! It comes back within 24 hours [1].")
        self.assertEqual(len(detail["draft_sources"]), 1)
