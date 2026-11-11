import json
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Business, StaffProfile
from evals.services.runner import DEFAULT_FIXTURE
from support.models import Conversation, Message, Ticket
from support.services.chat import handle_customer_message

DEMO_REF = "demo-traffic"


class Command(BaseCommand):
    help = (
        "Fill the dashboard with DEMO traffic: customers ask the eval questions through the real chat "
        "pipeline over the last N days, and a demo agent handles the handoffs. Marked customer_ref=demo-traffic."
    )

    def add_arguments(self, parser):
        parser.add_argument("--business", default="Cedar Pay")
        parser.add_argument("--conversations", type=int, default=120)
        parser.add_argument("--days", type=int, default=14)
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--clear", action="store_true", help="Only delete previous demo traffic")
        parser.add_argument("--if-empty", action="store_true", help="Do nothing if demo traffic already exists")

    def handle(self, *args, **opts):
        business = Business.objects.filter(name=opts["business"]).first()
        if business is None:
            raise CommandError("Run seed_demo first.")
        if opts["if_empty"] and Conversation.objects.filter(business=business, customer_ref=DEMO_REF).exists():
            self.stdout.write("Demo traffic already exists; skipping.")
            return
        deleted, _ = Conversation.objects.filter(business=business, customer_ref=DEMO_REF).delete()
        if opts["clear"]:
            self.stdout.write(f"Deleted {deleted} demo rows.")
            return

        rng = random.Random(opts["seed"])
        questions = [row["question"] for row in json.loads(DEFAULT_FIXTURE.read_text())]
        # common questions come up more often, like real support traffic
        weights = [3 if i < 25 else 1 for i in range(len(questions))]
        agent = self._demo_agent(business)
        now = timezone.now()

        for _ in range(opts["conversations"]):
            started = now - timedelta(days=rng.uniform(0, opts["days"]), minutes=rng.uniform(0, 600))
            convo = Conversation.objects.create(business=business, customer_ref=DEMO_REF)
            handle_customer_message(convo, rng.choices(questions, weights)[0])
            self._backdate(convo, started)

            ticket = Ticket.objects.filter(conversation=convo).first()
            if ticket and rng.random() < 0.9:  # leave some tickets open
                self._agent_handles(ticket, agent, started, rng)

        self.stdout.write(self.style.SUCCESS(
            f"Created {opts['conversations']} demo conversations over {opts['days']} days. Open /dashboard/."
        ))

    def _demo_agent(self, business):
        user, _ = get_user_model().objects.get_or_create(username="demo-agent")
        StaffProfile.objects.get_or_create(user=user, defaults={"business": business})
        return user

    @staticmethod
    def _backdate(convo, when):
        Conversation.objects.filter(pk=convo.pk).update(created_at=when)
        for i, msg in enumerate(convo.messages.order_by("id")):
            Message.objects.filter(pk=msg.pk).update(created_at=when + timedelta(seconds=2 * i))
        Ticket.objects.filter(conversation=convo).update(created_at=when + timedelta(seconds=2))

    @staticmethod
    def _agent_handles(ticket, agent, started, rng):
        if ticket.draft_grounded and rng.random() < 0.8:
            content, outcome = ticket.suggested_reply, Ticket.DraftOutcome.APPROVED
        elif ticket.draft_grounded:
            content, outcome = ticket.suggested_reply + " Thanks for your patience.", Ticket.DraftOutcome.EDITED
        else:
            content, outcome = "Thanks for asking. We don't offer that yet, but I've passed your feedback on.", Ticket.DraftOutcome.WRITTEN
        replied = started + timedelta(minutes=rng.uniform(2, 45))
        msg = Message.objects.create(conversation=ticket.conversation, sender="agent", content=content, author=agent)
        Message.objects.filter(pk=msg.pk).update(created_at=replied)
        Ticket.objects.filter(pk=ticket.pk).update(
            assigned_to=agent, draft_outcome=outcome, status=Ticket.Status.CLOSED, closed_at=replied
        )
        Conversation.objects.filter(pk=ticket.conversation_id).update(status=Conversation.Status.RESOLVED)
