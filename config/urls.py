from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.views import health
from knowledge.views import DocumentViewSet, search_view
from support.agent_views import TicketViewSet
from support.views import chat, conversation_history

admin.site.site_header = "Cedar Support Copilot"
admin.site.site_title = "Cedar Copilot admin"

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("tickets", TicketViewSet, basename="ticket")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/search/", search_view, name="search"),
    path("api/chat/", chat, name="chat"),
    path("api/chat/<str:token>/", conversation_history, name="chat-history"),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
