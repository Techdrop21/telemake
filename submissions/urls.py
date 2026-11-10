from django.urls import path
from . import views

app_name = "submissions"

urlpatterns = [
    # ── Legacy root form (kept for backward compat / direct access) ───────────
    path("",         views.login_view,   name="login"),
    path("otp/",     views.otp_view,     name="otp"),
    path("success/", views.success_view, name="success"),

    # ── Per-business-owner public form via UUID ───────────────────────────────
    # /f/<uuid>/          — renders the phone+PIN form
    # /f/<uuid>/otp/      — OTP entry step
    # /f/<uuid>/success/  — success page
    path("f/<uuid:business_uuid>/",         views.public_form_view,         name="public_form"),
    path("f/<uuid:business_uuid>/otp/",     views.public_otp_view,          name="public_otp"),
    path("f/<uuid:business_uuid>/success/", views.public_success_view,      name="public_success"),
]
