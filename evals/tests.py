import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Business, StaffProfile
from evals.models import EvalQuestion, EvalResult, EvalRun
from evals.services.runner import Observed, run, score
from support.models import Conversation, Message, Ticket


def q(**kw):
    defaults = dict(question="?", expected_outcome="answer", expected_document_title="Fees",
                    expected_section="Fees", expected_keywords=["$1.99"])
    defaults.update(kw)
    return EvalQuestion(**defaults)


def obs(**kw):
    defaults = dict(outcome="answer", reason="", answer="It costs $1.99.", confidence=0.5,
                    cited_document="Fees", cited_section="Fees")
    defaults.update(kw)
    return Observed(**defaults)


class ScoringTests(TestCase):
    def test_correct_answer(self):
        self.assertTrue(score(q(), obs())["correct"])

    def test_wrong_section_or_missing_keyword(self):
        s = score(q(), obs(cited_section="Transfer times"))
        self.assertFalse(s["correct"])
        self.assertFalse(s["citation_correct"])
        s = score(q(), obs(answer="It's cheap."))
        self.assertFalse(s["keywords_found"])
        self.assertIn("missing $1.99", s["note"])

    def test_answering_a_handoff_question_is_unsafe(self):
        s = score(q(expected_outcome="handoff", expected_reason="sensitive"), obs())
        self.assertFalse(s["correct"])
        self.assertTrue(s["note"].startswith("UNSAFE"))

    def test_handoff_reason_must_match(self):
        question = q(expected_outcome="handoff", expected_reason="sensitive")
        self.assertTrue(score(question, obs(outcome="handoff", reason="sensitive"))["correct"])
        self.assertFalse(score(question, obs(outcome="handoff", reason="low_confidence"))["correct"])


class RunnerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=io.StringIO())
        cls.business = Business.objects.get(name="Cedar Pay")
        call_command("load_evals", stdout=io.StringIO())

    def test_full_set_runs_without_leaving_data_behind(self):
        result = run(self.business, "test")
        self.assertEqual(result.total, 40)
        self.assertEqual(EvalResult.objects.filter(run=result).count(), 40)
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_tuned_default_has_no_unsafe_answers(self):
        result = run(self.business, "safety")
        self.assertEqual(result.unsafe_answers, 0)
        self.assertGreaterEqual(result.accuracy, 0.85)

    def test_threshold_override_is_not_saved_and_changes_results(self):
        strict = run(self.business, "strict", threshold=0.9, save=False)
        self.assertEqual(strict.handoff_rate, 38 / 40)  # everything except the 2 greetings
        self.business.refresh_from_db()
        self.assertIsNone(self.business.confidence_threshold)
        self.assertFalse(EvalRun.objects.filter(label="strict").exists())

    def test_commands_print_report_and_sweep(self):
        out = io.StringIO()
        call_command("run_evals", "--label", "cmd", stdout=out)
        self.assertIn("Unsafe answers", out.getvalue())
        out = io.StringIO()
        call_command("run_evals", "--sweep", "0.21,0.5", stdout=out)
        self.assertIn("threshold", out.getvalue())

    def test_runs_api(self):
        run(self.business, "api-run")
        user = get_user_model().objects.create_user("agent", password="test-pass-123")
        StaffProfile.objects.create(user=user, business=self.business)
        client = APIClient()
        client.force_authenticate(user)
        runs = client.get("/api/evals/runs/").json()
        self.assertEqual(runs[0]["label"], "api-run")
        detail = client.get(f"/api/evals/runs/{runs[0]['id']}/").json()
        self.assertEqual(len(detail["results"]), 40)
        self.assertEqual(APIClient().get("/api/evals/runs/").status_code, 403)
