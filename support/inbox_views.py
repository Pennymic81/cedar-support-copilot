"""Agent Inbox page: work through handed-off chats without the API or the Django admin."""
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Ticket
from .services.agent import AgentActionError, close_ticket, has_policy_draft, send_reply
from .services.drafts import draft_for_ticket


def _staff_business(request):
    if not request.user.is_authenticated:
        return None, redirect_to_login(request.get_full_path(), "/admin/login/")
    staff = getattr(request.user, "staff", None)
    if staff is None:
        return None, HttpResponseForbidden("Your account isn't linked to a business.")
    return staff.business, None


@require_http_methods(["GET", "POST"])
def inbox(request, ticket_id=None):
    business, denied = _staff_business(request)
    if denied:
        return denied

    show_closed = request.GET.get("show") == "closed"
    tickets = (
        Ticket.objects.filter(business=business)
        .select_related("conversation", "assigned_to")
        .order_by("created_at")
    )
    listed = tickets.filter(status=Ticket.Status.CLOSED) if show_closed else tickets.exclude(status=Ticket.Status.CLOSED)

    if ticket_id is None:
        first = listed.first()
        if first is not None:
            return redirect("inbox-ticket", ticket_id=first.id)
        return render(request, "support/inbox.html", {"business": business, "tickets": listed, "show_closed": show_closed})

    ticket = get_object_or_404(tickets.prefetch_related("draft_sources__document"), pk=ticket_id)

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action in {"send", "send_close"}:
                text = request.POST.get("reply", "").strip()
                if not text:
                    raise AgentActionError("Write a reply, or keep the suggested one in the box.")
                if has_policy_draft(ticket) and text == ticket.suggested_reply.strip():
                    send_reply(ticket, request.user, use_draft=True, close=action == "send_close")
                else:
                    send_reply(ticket, request.user, text, use_draft=has_policy_draft(ticket), close=action == "send_close")
                messages.success(request, "Reply sent. The customer sees it in their chat.")
            elif action == "close":
                close_ticket(ticket)
                messages.success(request, "Ticket closed. The chat is back with the AI.")
            elif action == "redraft":
                draft_for_ticket(ticket)
                messages.success(request, "Draft refreshed.")
        except AgentActionError as exc:
            messages.error(request, str(exc))
        return redirect("inbox-ticket", ticket_id=ticket.id)

    return render(
        request,
        "support/inbox.html",
        {
            "business": business,
            "tickets": listed,
            "show_closed": show_closed,
            "ticket": ticket,
            "chat": ticket.conversation.messages.all(),
            "policy_draft": has_policy_draft(ticket),
        },
    )
