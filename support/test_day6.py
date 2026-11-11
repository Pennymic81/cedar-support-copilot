import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Business, StaffProfile
from support.models import Conversation, Ticket


class WidgetEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=io.StringIO())
        cls.business = Business.objects.get(name="Cedar Pay")

    def test_chat_allows_cross_origin_calls(self):
        pre = self.client.options("/api/chat/", HTTP_ORIGIN="https://shop.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
        self.assertEqual(pre.status_code, 204)
        self.assertEqual(pre["Access-Control-Allow-Origin"], "*")
        resp = self.client.post(
            "/api/chat/", {"widget_key": self.business.widget_key, "message": "Can I cancel a transfer?"},
            content_type="application/json", HTTP_ORIGIN="https://shop.example",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Access-Control-Allow-Origin"], "*")

    def test_staff_api_does_not_get_cors_headers(self):
        resp = self.client.get("/api/tickets/", HTTP_ORIGIN="https://evil.example")
        self.assertNotIn("Access-Control-Allow-Origin", resp)

    def test_chat_ignores_logged_in_session_and_csrf(self):
        user = get_user_model().objects.create_user("staffer", password="test-pass-123")
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        resp = csrf_client.post(
            "/api/chat/", {"widget_key": self.business.widget_key, "message": "Can I cancel a transfer?"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_demo_page_embeds_widget_with_key(self):
        html = self.client.get("/").content.decode()
        self.assertIn("widget/cedar-widget.js", html)
        self.assertIn(self.business.widget_key, html)
        self.assertIn("Demo brand", html)


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=io.StringIO())
        cls.business = Business.objects.get(name="Cedar Pay")
        cls.agent = get_user_model().objects.create_user("agent1", password="test-pass-123")
        StaffProfile.objects.create(user=cls.agent, business=cls.business)

    def test_dashboard_requires_staff_login(self):
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        outsider = get_user_model().objects.create_user("nobody", password="test-pass-123")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get("/dashboard/").status_code, 403)
        self.client.force_login(self.agent)
        self.assertContains(self.client.get("/dashboard/"), "How support is going")

    def test_analytics_counts_traffic(self):
        call_command("simulate_traffic", "--conversations", "40", stdout=io.StringIO())
        api = APIClient()
        api.force_authenticate(self.agent)
        d = api.get("/api/analytics/", {"days": 30}).json()
        self.assertEqual(d["conversations"], 40)
        self.assertEqual(d["resolved_by_ai"] + d["handed_off"], 40)
        self.assertEqual(d["handed_off"], Ticket.objects.count())
        self.assertAlmostEqual(d["ai_resolution_rate"] + d["handoff_rate"], 1.0, places=3)
        self.assertEqual(sum(d["handoff_reasons"].values()), d["handed_off"])
        self.assertTrue(d["top_topics"])
        self.assertIsNotNone(d["median_minutes_to_agent_reply"])
        self.assertEqual(sum(x["total"] for x in d["daily"]), 40)

    def test_analytics_scoped_and_protected(self):
        call_command("simulate_traffic", "--conversations", "5", stdout=io.StringIO())
        other = Business.objects.create(name="Other")
        outsider = get_user_model().objects.create_user("outsider", password="test-pass-123")
        StaffProfile.objects.create(user=outsider, business=other)
        api = APIClient()
        api.force_authenticate(outsider)
        self.assertEqual(api.get("/api/analytics/").json()["conversations"], 0)
        self.assertEqual(APIClient().get("/api/analytics/").status_code, 403)

    def test_simulate_traffic_clear(self):
        call_command("simulate_traffic", "--conversations", "5", stdout=io.StringIO())
        call_command("simulate_traffic", "--clear", stdout=io.StringIO())
        self.assertEqual(Conversation.objects.count(), 0)
