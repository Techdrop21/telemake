import json
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import BusinessLoginForm, BusinessRegistrationForm
from .models import PLAN_CATALOGUE, BusinessOwner, Payment, Subscription, TelegramConfiguration
from .payhero import (
    check_transaction_status,
    initiate_stk_push,
    normalise_phone,
    parse_callback,
)
from submissions.services import test_telegram_connection

logger = logging.getLogger(__name__)


def _base_context(business_owner):
    """Shared context vars required by dashboard_base.html."""
    try:
        tg = business_owner.telegram_config
        telegram_configured = bool(tg.bot_token and tg.chat_id and tg.is_active)
    except TelegramConfiguration.DoesNotExist:
        telegram_configured = False
    return {
        "telegram_configured": telegram_configured,
        "subscription_active": business_owner.subscription.is_active(),
    }


def register_view(request):
    """
    Business owner registration.
    Creates User account, BusinessOwner profile, and inactive Subscription.
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = BusinessRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                business_owner = BusinessOwner.objects.create(
                    user=user,
                    business_name=form.cleaned_data["business_name"],
                    phone=form.cleaned_data.get("phone", ""),
                )
                # Create inactive subscription record
                Subscription.objects.create(
                    business_owner=business_owner,
                    status="inactive",
                )
                # Log the user in
                login(request, user)
                messages.success(request, f"Welcome! Your account has been created.")
                return redirect("accounts:dashboard")
    else:
        form = BusinessRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    """Business owner login."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = BusinessLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, "Welcome back!")
                next_url = request.GET.get("next", "accounts:dashboard")
                return redirect(next_url)
            else:
                messages.error(request, "Invalid email or password.")
    else:
        form = BusinessLoginForm()

    return render(request, "accounts/login.html", {"form": form})


@login_required
def logout_view(request):
    """Log out the current user."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")


# ── Dashboard Views ───────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    business_owner = request.user.business_profile
    subscription = business_owner.subscription
    total_submissions = business_owner.submissions.count()

    try:
        tg = business_owner.telegram_config
        telegram_configured = bool(tg.bot_token and tg.chat_id and tg.is_active)
    except TelegramConfiguration.DoesNotExist:
        telegram_configured = False

    context = {
        "business_owner": business_owner,
        "subscription": subscription,
        "total_submissions": total_submissions,
        "public_form_url": request.build_absolute_uri(business_owner.get_public_form_url()),
        "telegram_configured": telegram_configured,
        "subscription_active": subscription.is_active(),
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def telegram_config_view(request):
    """
    Telegram configuration page.
    Allows business owner to set/update their Telegram bot credentials.
    """
    business_owner = request.user.business_profile

    try:
        telegram_config = business_owner.telegram_config
    except TelegramConfiguration.DoesNotExist:
        telegram_config = None

    if request.method == "POST":
        bot_token = request.POST.get("bot_token", "").strip()
        chat_id = request.POST.get("chat_id", "").strip()

        if not bot_token or not chat_id:
            messages.error(request, "Both bot token and chat ID are required.")
        else:
            if telegram_config:
                telegram_config.bot_token = bot_token
                telegram_config.chat_id = chat_id
                telegram_config.save()
                messages.success(request, "Telegram configuration updated successfully.")
            else:
                TelegramConfiguration.objects.create(
                    business_owner=business_owner,
                    bot_token=bot_token,
                    chat_id=chat_id,
                )
                messages.success(request, "Telegram configuration saved successfully.")
            return redirect("accounts:telegram_config")

    context = {
        "business_owner": business_owner,
        "telegram_config": telegram_config,
        **_base_context(business_owner),
    }
    return render(request, "accounts/telegram_config.html", context)


@login_required
def form_settings_view(request):
    """
    Public form settings page.
    Shows the unique public form URL and allows copying it.
    """
    business_owner = request.user.business_profile
    public_form_url = request.build_absolute_uri(business_owner.get_public_form_url())

    context = {
        "business_owner": business_owner,
        "public_form_url": public_form_url,
        **_base_context(business_owner),
    }
    return render(request, "accounts/form_settings.html", context)


@login_required
def account_settings_view(request):
    """
    Account settings page.
    Allows updating profile information and password.
    """
    business_owner = request.user.business_profile

    if request.method == "POST":
        # Update business name and phone
        business_owner.business_name = request.POST.get("business_name", business_owner.business_name)
        business_owner.phone = request.POST.get("phone", business_owner.phone)
        business_owner.save()

        # Update email if changed
        new_email = request.POST.get("email", "").strip()
        if new_email and new_email != request.user.email:
            request.user.email = new_email
            request.user.username = new_email  # Keep username in sync
            request.user.save()

        messages.success(request, "Account settings updated successfully.")
        return redirect("accounts:account_settings")

    context = {
        "business_owner": business_owner,
        **_base_context(business_owner),
    }
    return render(request, "accounts/account_settings.html", context)


@login_required
def billing_view(request):
    """
    Billing and subscription management page.
    Shows current plan, payment status, expiry, and payment history.
    """
    business_owner = request.user.business_profile
    subscription = business_owner.subscription
    payments = business_owner.payments.order_by("-created_at")[:20]

    # Pre-compute the local 9-digit number for the payment modal phone field.
    # Strip all non-digits from the stored phone, then take the last 9 digits.
    raw_phone = business_owner.phone or ""
    digits = "".join(c for c in raw_phone if c.isdigit())
    phone_local = digits[-9:] if len(digits) >= 9 else digits

    context = {
        "business_owner": business_owner,
        "subscription": subscription,
        "payments": payments,
        "plan_catalogue": PLAN_CATALOGUE,
        "phone_local": phone_local,
        **_base_context(business_owner),
    }
    return render(request, "accounts/billing.html", context)


# ── Pricing (public) ──────────────────────────────────────────────────────────

def pricing_view(request):
    """
    Public pricing page — no auth required.
    Displays the three plans with savings callouts.
    """
    return render(request, "accounts/pricing.html", {
        "plan_catalogue": PLAN_CATALOGUE,
        "user": request.user,
    })


# ── Payment initiation ────────────────────────────────────────────────────────

@login_required
@require_POST
def initiate_payment_view(request):
    """
    POST /dashboard/billing/pay/
    Validates plan + phone, creates a Payment row, fires the STK push.
    Submission is saved BEFORE calling PayHero so a crash mid-request still
    leaves a recoverable pending record.
    """
    business_owner = request.user.business_profile
    plan_key = request.POST.get("plan", "").strip()
    phone_raw = request.POST.get("phone", "").strip()

    # ── Validate plan ────────────────────────────────────────────────────────
    if plan_key not in PLAN_CATALOGUE:
        messages.error(request, "Invalid plan selected.")
        return redirect("accounts:billing")

    plan_info = PLAN_CATALOGUE[plan_key]
    amount = int(plan_info["price"])  # PayHero expects integer KES

    # ── Validate phone ───────────────────────────────────────────────────────
    if not phone_raw:
        # Fall back to the phone stored on the account
        phone_raw = business_owner.phone
    if not phone_raw:
        messages.error(request, "Please enter the M-Pesa phone number to charge.")
        return redirect("accounts:billing")

    phone = normalise_phone(phone_raw)
    if not phone.startswith("254") or len(phone) != 12:
        messages.error(request, "Enter a valid Kenyan phone number (e.g. 0712 345 678).")
        return redirect("accounts:billing")

    # ── Build callback URL ───────────────────────────────────────────────────
    callback_url = request.build_absolute_uri("/payments/callback/")

    # ── Create Payment row (pending) BEFORE calling PayHero ─────────────────
    external_ref = Payment.generate_reference(business_owner.pk)
    payment = Payment.objects.create(
        business_owner=business_owner,
        plan=plan_key,
        amount=plan_info["price"],
        phone=phone,
        external_reference=external_ref,
        status="pending",
    )

    # ── Fire STK push ────────────────────────────────────────────────────────
    result = initiate_stk_push(
        amount=amount,
        phone=phone,
        external_reference=external_ref,
        callback_url=callback_url,
        customer_name=business_owner.business_name,
    )

    if result.success:
        payment.payhero_reference = result.payhero_reference
        payment.status = "queued"
        payment.save(update_fields=["payhero_reference", "status"])

        logger.info(
            "STK push queued for %s — plan=%s amount=%s ref=%s",
            business_owner.business_name, plan_key, amount, external_ref,
        )
        messages.success(
            request,
            f"M-Pesa prompt sent to {phone_raw}. Enter your PIN to complete the payment.",
        )
        # Redirect to a polling page so the user sees the outcome
        return redirect("accounts:payment_status", pk=payment.pk)
    else:
        payment.status = "failed"
        payment.result_description = result.error
        payment.completed_at = timezone.now()
        payment.save(update_fields=["status", "result_description", "completed_at"])

        logger.error(
            "STK push failed for %s ref=%s: %s",
            business_owner.business_name, external_ref, result.error,
        )
        messages.error(request, f"Could not send payment prompt: {result.error}")
        return redirect("accounts:billing")


# ── PayHero webhook callback ──────────────────────────────────────────────────

@csrf_exempt
def payhero_callback_view(request):
    """
    POST /payments/callback/
    PayHero calls this after the customer completes or cancels the M-Pesa prompt.
    Must always respond 200 — PayHero does not retry on 4xx/5xx.
    Processing is idempotent: a SUCCESS payment can never be overwritten.
    No Django auth — PayHero is a server and sends no session/CSRF.
    """
    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        logger.error("PayHero callback: invalid JSON body")
        return JsonResponse({"status": "ok"})  # still 200

    result = parse_callback(body)
    if result is None:
        return JsonResponse({"status": "ok"})

    try:
        payment = Payment.objects.select_related("business_owner__subscription").get(
            external_reference=result.external_reference
        )
    except Payment.DoesNotExist:
        logger.warning(
            "PayHero callback: unknown external_reference=%s", result.external_reference
        )
        return JsonResponse({"status": "ok"})

    # Idempotency guard — once SUCCESS, nothing moves it
    if payment.status == "success":
        logger.info("PayHero callback: duplicate for already-succeeded ref=%s", result.external_reference)
        return JsonResponse({"status": "ok"})

    with transaction.atomic():
        payment.status = result.status
        payment.mpesa_receipt = result.mpesa_receipt
        payment.result_description = result.result_description
        payment.completed_at = timezone.now()
        payment.save(update_fields=["status", "mpesa_receipt", "result_description", "completed_at"])

        if result.status == "success":
            subscription = payment.business_owner.subscription
            subscription.activate(
                plan_key=payment.plan,
                payment_reference=result.mpesa_receipt or payment.external_reference,
                amount=payment.amount,
            )
            logger.info(
                "Subscription activated for %s — plan=%s receipt=%s",
                payment.business_owner.business_name,
                payment.plan,
                result.mpesa_receipt,
            )
        else:
            logger.info(
                "PayHero callback: ref=%s status=%s desc=%s",
                result.external_reference, result.status, result.result_description,
            )

    return JsonResponse({"status": "ok"})


# ── Payment status polling ────────────────────────────────────────────────────

@login_required
def payment_status_view(request, pk):
    """
    GET  /dashboard/billing/pay/<pk>/status/
         Renders a waiting page; JS polls the JSON endpoint below.
    """
    business_owner = request.user.business_profile
    try:
        payment = business_owner.payments.get(pk=pk)
    except Payment.DoesNotExist:
        messages.error(request, "Payment not found.")
        return redirect("accounts:billing")

    return render(request, "accounts/payment_status.html", {
        "business_owner": business_owner,
        "payment": payment,
        "plan_info": PLAN_CATALOGUE.get(payment.plan, {}),
        **_base_context(business_owner),
    })


@login_required
def payment_status_json_view(request, pk):
    """
    GET /dashboard/billing/pay/<pk>/json/
    JSON endpoint polled by the payment_status page every 3 s.
    If the payment is still pending/queued after the client has been polling
    for a while, we ask PayHero directly (manual verify) so stale payments
    don't stay unresolved forever.
    """
    business_owner = request.user.business_profile
    try:
        payment = business_owner.payments.get(pk=pk)
    except Payment.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)

    # If still in a transient state and we have a PayHero reference, ask them
    if payment.status in ("pending", "queued") and payment.payhero_reference:
        status_result = check_transaction_status(payment.payhero_reference)
        if status_result.status in ("success", "failed", "cancelled"):
            with transaction.atomic():
                # Only update if not already SUCCESS (idempotency)
                payment.refresh_from_db()
                if payment.status != "success":
                    payment.status = status_result.status
                    payment.mpesa_receipt = status_result.mpesa_receipt
                    payment.result_description = status_result.result_description or "Resolved via status check"
                    payment.completed_at = timezone.now()
                    payment.save(update_fields=[
                        "status", "mpesa_receipt", "result_description", "completed_at"
                    ])
                    if status_result.status == "success":
                        subscription = payment.business_owner.subscription
                        subscription.activate(
                            plan_key=payment.plan,
                            payment_reference=status_result.mpesa_receipt or payment.external_reference,
                            amount=payment.amount,
                        )

    return JsonResponse({
        "status": payment.status,
        "mpesa_receipt": payment.mpesa_receipt,
        "result_description": payment.result_description,
        "plan": payment.plan,
        "amount": str(payment.amount),
    })


@login_required
def test_telegram_view(request):
    """
    POST-only endpoint — sends a test message using the owner's saved Telegram config.
    Returns the user to the Telegram config page with a success or error message.
    """
    if request.method != "POST":
        return redirect("accounts:telegram_config")

    business_owner = request.user.business_profile

    try:
        config = business_owner.telegram_config
    except TelegramConfiguration.DoesNotExist:
        messages.error(request, "No Telegram configuration found. Please save your settings first.")
        return redirect("accounts:telegram_config")

    if not config.bot_token or not config.chat_id:
        messages.error(request, "Bot token and chat ID are required before testing.")
        return redirect("accounts:telegram_config")

    success, message = test_telegram_connection(config.bot_token, config.chat_id)
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("accounts:telegram_config")
