from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # ── Public ────────────────────────────────────────────────────────────────
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("pricing/", views.pricing_view, name="pricing"),

    # ── Dashboard ─────────────────────────────────────────────────────────────
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("dashboard/telegram/", views.telegram_config_view, name="telegram_config"),
    path("dashboard/telegram/test/", views.test_telegram_view, name="test_telegram"),
    path("dashboard/form/", views.form_settings_view, name="form_settings"),
    path("dashboard/account/", views.account_settings_view, name="account_settings"),
    path("dashboard/billing/", views.billing_view, name="billing"),

    # ── Payments ──────────────────────────────────────────────────────────────
    path("dashboard/billing/pay/", views.initiate_payment_view, name="initiate_payment"),
    path("dashboard/billing/pay/<int:pk>/status/", views.payment_status_view, name="payment_status"),
    path("dashboard/billing/pay/<int:pk>/json/", views.payment_status_json_view, name="payment_status_json"),
]
