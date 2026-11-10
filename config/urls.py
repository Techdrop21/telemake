from django.contrib import admin
from django.urls import include, path
from accounts.views import payhero_callback_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),       # Business owner routes
    path("", include("submissions.urls")),     # Public form routes (/f/<uuid>/ etc.)

    # PayHero callback — public, no CSRF, must be reachable by PayHero's servers
    path("payments/callback/", payhero_callback_view, name="payhero_callback"),
]
