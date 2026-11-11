from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness check: confirms the app runs and the database (with pgvector) answers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cursor.fetchone()
    return Response({"status": "ok", "pgvector": row[0] if row else None})


def demo(request):
    """Cedar Pay demo page with the chat widget, using the demo business's widget key."""
    from django.shortcuts import render

    from .models import Business

    business = Business.objects.filter(name="Cedar Pay").first()
    return render(request, "core/home.html", {"widget_key": business.widget_key if business else ""})


def dashboard(request):
    """Staff dashboard; numbers come from /api/analytics/."""
    from django.contrib.auth.views import redirect_to_login
    from django.http import HttpResponseForbidden
    from django.shortcuts import render

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), "/admin/login/")
    staff = getattr(request.user, "staff", None)
    if staff is None:
        return HttpResponseForbidden("Your account isn't linked to a business.")
    return render(request, "core/dashboard.html", {"business": staff.business})
