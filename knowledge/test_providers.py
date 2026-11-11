"""Gemini and other hosted providers, with the network mocked."""
import hashlib
import math
from io import StringIO
from unittest import mock

import requests
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from core.http import post_json
from core.models import Business
from evals.services.runner import current_config, load_questions
from knowledge.models import Document
from knowledge.services import embeddings
from knowledge.services.calibrate import calibrate
from knowledge.services.embeddings import GeminiEmbedder, LocalHashEmbedder, get_embedder
from knowledge.services.ingest import ingest_document, reembed_document, search
from support.services.llm import LLMError, LocalAnswerer, OpenAICompatibleAnswerer, get_answerer

GEMINI = dict(EMBEDDING_PROVIDER="gemini", EMBEDDING_MODEL="gemini-embedding-001", LLM_API_KEY="test-key")


def response(status=200, body=None, headers=None):
    r = requests.Response()
    r.status_code = status
    r._content = __import__("json").dumps(body or {}).encode()
    r.headers.update(headers or {})
    return r


def fake_vector(text, dims=1536):
    """Deterministic stand-in for Gemini: reuse the local embedder so similar texts stay similar."""
    return LocalHashEmbedder(dims)._vector(text)


def fake_gemini(url, headers, json, timeout):
    vecs = [{"values": [x * 3 for x in fake_vector(r["content"]["parts"][0]["text"])]} for r in json["requests"]]
    return response(body={"embeddings": vecs})


class RetryTests(SimpleTestCase):
    @mock.patch("core.http.time.sleep")
    @mock.patch("core.http.requests.post")
    def test_retries_rate_limits_then_succeeds(self, post, sleep):
        post.side_effect = [response(429, headers={"Retry-After": "3"}), response(503), response(body={"ok": 1})]
        self.assertEqual(post_json("https://x", headers={}, payload={}), {"ok": 1})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [3.0, 4.0])

    @mock.patch("core.http.time.sleep")
    @mock.patch("core.http.requests.post", return_value=response(429, headers={"Retry-After": "5"}))
    def test_gives_up_after_max_wait(self, post, sleep):
        with self.assertRaises(requests.HTTPError):
            post_json("https://x", headers={}, payload={}, max_wait=8)
        self.assertEqual(sleep.call_count, 1)

    @mock.patch("core.http.requests.post", return_value=response(400))
    def test_client_errors_are_not_retried(self, post):
        with self.assertRaises(requests.HTTPError):
            post_json("https://x", headers={}, payload={})
        self.assertEqual(post.call_count, 1)


class GeminiEmbedderTests(SimpleTestCase):
    @mock.patch("core.http.requests.post", side_effect=fake_gemini)
    def test_request_shape_and_normalised_output(self, post):
        out = GeminiEmbedder("k", "gemini-embedding-001", 1536).embed(["a b", "c"], kind="query")
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        self.assertTrue(url.endswith("/models/gemini-embedding-001:batchEmbedContents"))
        self.assertEqual(kwargs["headers"], {"x-goog-api-key": "k"})
        req = kwargs["json"]["requests"][0]
        self.assertEqual(req["taskType"], "RETRIEVAL_QUERY")
        self.assertEqual(req["outputDimensionality"], 1536)
        self.assertEqual(req["model"], "models/gemini-embedding-001")
        self.assertAlmostEqual(math.sqrt(sum(v * v for v in out[0])), 1.0, places=6)

    @mock.patch("core.http.requests.post", side_effect=fake_gemini)
    def test_documents_use_document_task_and_batches(self, post):
        GeminiEmbedder("k", "m", 1536, batch_size=2).embed(["a", "b", "c"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["json"]["requests"][0]["taskType"], "RETRIEVAL_DOCUMENT")

    @mock.patch("core.http.requests.post", return_value=response(body={"embeddings": [{"values": [1.0, 0.0]}]}))
    def test_wrong_size_is_an_error(self, post):
        with self.assertRaises(embeddings.EmbeddingError):
            GeminiEmbedder("k", "m", 1536).embed(["a"])

    @override_settings(EMBEDDING_PROVIDER="gemini", LLM_API_KEY="")
    def test_missing_key_falls_back_to_local(self):
        self.assertIsInstance(get_embedder(), LocalHashEmbedder)


class AnswererTests(SimpleTestCase):
    def chat_body(self, content, finish="stop"):
        return response(body={"choices": [{"message": {"content": content}, "finish_reason": finish}]})

    @mock.patch("core.http.requests.post")
    def test_sends_reasoning_effort_and_budget(self, post):
        post.return_value = self.chat_body("Fees are $1.99 [1].")
        a = OpenAICompatibleAnswerer("k", "https://g/v1beta/openai/", "gemini-3.8-flash", reasoning_effort="low",
                                     max_tokens=2048)
        self.assertEqual(a.complete([{"role": "user", "content": "hi"}]), "Fees are $1.99 [1].")
        self.assertEqual(post.call_args.args[0], "https://g/v1beta/openai/chat/completions")
        body = post.call_args.kwargs["json"]
        self.assertEqual((body["reasoning_effort"], body["max_tokens"]), ("low", 2048))

    @mock.patch("core.http.requests.post")
    def test_empty_content_is_an_error(self, post):
        post.return_value = self.chat_body(None, finish="length")
        with self.assertRaisesRegex(LLMError, "length"):
            OpenAICompatibleAnswerer("k", "https://g", "m").complete([])

    @override_settings(LLM_PROVIDER="openai", LLM_API_KEY="")
    def test_missing_key_falls_back_to_local(self):
        self.assertIsInstance(get_answerer(), LocalAnswerer)


@mock.patch("core.http.requests.post", side_effect=fake_gemini)
class SwitchingModelsTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Cedar Pay")
        self.doc = Document.objects.create(business=self.business, title="Fees", source_type="text")
        ingest_document(self.doc, text="# Fees\n\nSending money abroad costs $1.99 per transfer.")

    def test_search_ignores_vectors_from_another_model_until_reembedded(self, post):
        self.assertEqual(self.doc.embedding_signature, "local-hash:1536")
        with override_settings(**GEMINI):
            self.assertEqual(search(self.business, "transfer fee"), [])
            self.assertTrue(reembed_document(self.doc))
            self.assertFalse(reembed_document(self.doc))  # already current
            results = search(self.business, "transfer fee")
        self.assertEqual(results[0].document, self.doc)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.embedding_signature, "gemini:gemini-embedding-001:1536")

    def test_reembed_command(self, post):
        with override_settings(**GEMINI):
            out = StringIO()
            call_command("reembed", stdout=out)
            self.assertIn("re-embedded  Fees", out.getvalue())
            out = StringIO()
            call_command("reembed", stdout=out)
            self.assertIn("already use", out.getvalue())

    def test_failed_reembed_keeps_old_vectors(self, post):
        post.side_effect = requests.ConnectionError("down")
        with override_settings(**GEMINI), self.assertRaises(embeddings.EmbeddingError):
            reembed_document(self.doc)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.embedding_signature, "local-hash:1536")


class CalibrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())
        cls.business = Business.objects.get(name="Cedar Pay")
        load_questions(cls.business)

    def test_threshold_separates_answerable_from_off_topic(self):
        result = calibrate(self.business)
        self.assertGreaterEqual(result.correct / result.total, 0.85)
        self.assertGreater(result.threshold, 0)

    def test_command_skips_offline_embedder_and_saves_otherwise(self):
        out = StringIO()
        call_command("calibrate_threshold", stdout=out)
        self.assertIn("Offline embedder", out.getvalue())
        call_command("calibrate_threshold", "--force", stdout=StringIO())
        self.business.refresh_from_db()
        self.assertIsNotNone(self.business.confidence_threshold)

    def test_eval_config_changes_with_the_model(self):
        local = current_config(self.business)
        with override_settings(**GEMINI, LLM_PROVIDER="openai", LLM_CHAT_MODEL="gemini-3.8-flash"):
            hosted = current_config(self.business)
        self.assertEqual(local["llm"], "local")
        self.assertEqual(hosted["llm"], "gemini-3.8-flash")
        self.assertNotEqual(local["embedding"], hosted["embedding"])


class ProviderOutageTests(TestCase):
    def test_chat_hands_off_when_embeddings_are_down(self):
        from support.models import Conversation, Ticket
        from support.services.chat import handle_customer_message

        business = Business.objects.create(name="Cedar Pay")
        convo = Conversation.objects.create(business=business, customer_ref="t")
        with override_settings(**GEMINI), mock.patch(
            "core.http.requests.post", side_effect=requests.ConnectionError("down")
        ):
            result = handle_customer_message(convo, "How long does a transfer to Spain take?")
        self.assertTrue(result.handed_off)
        self.assertEqual(Ticket.objects.get(conversation=convo).reason, Ticket.Reason.LOW_CONFIDENCE)
