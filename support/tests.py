import io
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Business
from support.models import Conversation, MessageCitation, Ticket
from support.services import llm
from support.services.chat import wants_a_person


class HelperTests(SimpleTestCase):
    def test_parse_citations_keeps_valid_unique_numbers(self):
        self.assertEqual(llm.parse_citations("Yes [2]. Also [1][2] and [9].", 3), [2, 1])

    def test_strip_heading(self):
        self.assertEqual(llm.strip_heading("## Fees\n\nIt costs $1.99."), "It costs $1.99.")

    def test_wants_a_person(self):
        self.assertTrue(wants_a_person("Can I talk to a person please?"))
        self.assertTrue(wants_a_person("I want a human agent"))
        self.assertFalse(wants_a_person("How much is a transfer?"))


class ChatApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=io.StringIO())
        cls.business = Business.objects.get(name="Cedar Pay")

    def setUp(self):
        self.client = APIClient()

    def send(self, message, token=None, key=None):
        body = {"widget_key": key or self.business.widget_key, "message": message}
        if token:
            body["conversation_token"] = token
        return self.client.post("/api/chat/", body, format="json")

    def test_answers_with_citation_from_the_right_section(self):
        resp = self.send("How long does a transfer to Spain take?")
        self.assertEqual(resp.status_code, 200)
        reply = resp.json()["reply"]
        self.assertFalse(reply["handed_off"])
        self.assertIn("Spain", reply["content"])
        self.assertEqual(reply["citations"][0]["document_title"], "Fees and transfer times")
        self.assertEqual(reply["citations"][0]["section"], "Transfer times")
        self.assertEqual(MessageCitation.objects.count(), 1)

    def test_unknown_topic_hands_off_with_a_ticket(self):
        resp = self.send("Do you offer car loans?")
        reply = resp.json()["reply"]
        self.assertTrue(reply["handed_off"])
        self.assertEqual(reply["citations"], [])
        self.assertEqual(resp.json()["status"], "escalated")
        ticket = Ticket.objects.get()
        self.assertEqual(ticket.reason, Ticket.Reason.LOW_CONFIDENCE)

    def test_asking_for_a_person_hands_off(self):
        resp = self.send("Can I talk to a person please?")
        self.assertTrue(resp.json()["reply"]["handed_off"])
        self.assertIn("Of course", resp.json()["reply"]["content"])
        self.assertEqual(Ticket.objects.get().reason, Ticket.Reason.CUSTOMER_REQUESTED)

    def test_ai_stays_quiet_after_a_person_is_requested(self):
        token = self.send("Can I talk to a person please?").json()["conversation_token"]
        resp = self.send("How much does a transfer cost?", token=token)
        self.assertTrue(resp.json()["reply"]["handed_off"])
        self.assertIn("member of our team", resp.json()["reply"]["content"])
        self.assertEqual(Ticket.objects.count(), 1)

    def test_greetings_and_thanks_get_a_reply_without_a_ticket(self):
        for text in ["hi", "Hello!", "good morning", "thanks!", "ok"]:
            reply = self.send(text).json()["reply"]
            self.assertFalse(reply["handed_off"], text)
            self.assertIn("help", reply["content"], text)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_hi_then_a_real_question_is_answered(self):
        token = self.send("hi").json()["conversation_token"]
        reply = self.send("How long does a transfer to Spain take?", token=token).json()["reply"]
        self.assertFalse(reply["handed_off"])
        self.assertEqual(reply["citations"][0]["section"], "Transfer times")

    def test_ai_keeps_helping_after_a_not_sure_handoff(self):
        token = self.send("Do you offer car loans?").json()["conversation_token"]
        answered = self.send("How long does a transfer to Spain take?", token=token).json()
        self.assertFalse(answered["reply"]["handed_off"])
        self.assertEqual(answered["status"], "escalated")  # the team still has the loan question
        unsure = self.send("Can I get a mortgage?", token=token).json()["reply"]
        self.assertIn("either", unsure["content"])
        self.assertEqual(Ticket.objects.count(), 1)

    def test_money_problem_after_not_sure_handoff_upgrades_the_ticket(self):
        token = self.send("Do you offer car loans?").json()["conversation_token"]
        self.send("I was charged twice for a transfer", token=token)
        ticket = Ticket.objects.get()
        self.assertEqual(ticket.reason, Ticket.Reason.SENSITIVE)
        quiet = self.send("How long does a transfer to Spain take?", token=token).json()["reply"]
        self.assertIn("member of our team", quiet["content"])

    def test_ai_goes_quiet_once_an_agent_replies(self):
        from support.models import Message as Msg

        token = self.send("Do you offer car loans?").json()["conversation_token"]
        convo = Conversation.objects.get(token=token)
        Msg.objects.create(conversation=convo, sender="agent", content="Not yet, sorry!")
        reply = self.send("How long does a transfer to Spain take?", token=token).json()["reply"]
        self.assertIn("member of our team", reply["content"])

    def test_conversation_continues_and_history_is_readable_with_token(self):
        token = self.send("How long does a transfer to Spain take?").json()["conversation_token"]
        self.send("Can I cancel a transfer?", token=token)
        history = self.client.get(f"/api/chat/{token}/", {"widget_key": self.business.widget_key}).json()
        self.assertEqual([m["sender"] for m in history["messages"]], ["customer", "ai", "customer", "ai"])
        self.assertEqual(history["messages"][1]["citations"][0]["section"], "Transfer times")
        self.assertEqual(Conversation.objects.count(), 1)

    def test_bad_widget_key_and_token_are_rejected(self):
        self.assertEqual(self.send("hi", key="wrong").status_code, 403)
        self.assertEqual(self.send("hi", token="not-a-real-token").status_code, 404)
        token = self.send("Can I cancel a transfer?").json()["conversation_token"]
        other = Business.objects.create(name="Other")
        self.assertEqual(self.client.get(f"/api/chat/{token}/", {"widget_key": other.widget_key}).status_code, 404)

    def test_empty_message_is_rejected(self):
        self.assertEqual(self.send("   ").status_code, 400)

    @override_settings(LLM_PROVIDER="openai", LLM_API_KEY="test-key")
    def test_openai_provider_uses_model_answer_and_its_citations(self):
        fake = mock.Mock()
        fake.json.return_value = {"choices": [{"message": {"content": "They arrive within minutes [1]."}}]}
        fake.raise_for_status.return_value = None
        with mock.patch("support.services.llm.requests.post", return_value=fake) as post:
            reply = self.send("How long does a transfer to Spain take?").json()["reply"]
        self.assertEqual(reply["content"], "They arrive within minutes [1].")
        self.assertEqual(reply["citations"][0]["section"], "Transfer times")
        sent = post.call_args.kwargs["json"]
        self.assertIn("Answer ONLY from the numbered sources", sent["messages"][0]["content"])
        self.assertIn("Spain", sent["messages"][0]["content"])

    @override_settings(LLM_PROVIDER="openai", LLM_API_KEY="test-key")
    def test_model_saying_no_answer_hands_off(self):
        fake = mock.Mock()
        fake.json.return_value = {"choices": [{"message": {"content": llm.NO_ANSWER}}]}
        fake.raise_for_status.return_value = None
        with mock.patch("support.services.llm.requests.post", return_value=fake):
            reply = self.send("How long does a transfer to Spain take?").json()["reply"]
        self.assertTrue(reply["handed_off"])

    @override_settings(LLM_PROVIDER="openai", LLM_API_KEY="test-key")
    def test_model_outage_hands_off_instead_of_failing(self):
        import requests

        with mock.patch("support.services.llm.requests.post", side_effect=requests.ConnectionError("down")):
            resp = self.send("How long does a transfer to Spain take?")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["reply"]["handed_off"])

    def test_business_threshold_overrides_default(self):
        self.business.confidence_threshold = 0.99
        self.business.save()
        self.assertTrue(self.send("Can I cancel a transfer?").json()["reply"]["handed_off"])
