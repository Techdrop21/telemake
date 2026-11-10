"""
PayHero STK Push integration.

All PayHero-specific wire format knowledge lives here.
Nothing outside this module should know about PayHero's API shape.

API base:  https://backend.payhero.co.ke/api/v2/
Auth:      Authorization: Basic <base64(username:password)>
Docs ref:  https://docs.payhero.co.ke  (verified 2026-09-03 via Mwashelvix/Payment_STK_Push)
"""

import base64
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PAYHERO_API_BASE = "https://backend.payhero.co.ke/api/v2"
REQUEST_TIMEOUT = 15  # seconds


# ── Auth header ───────────────────────────────────────────────────────────────

def _auth_header() -> dict:
    """
    Build the Basic auth header from PAYHERO_USERNAME / PAYHERO_PASSWORD.
    If PAYHERO_BASIC_AUTH_TOKEN is set, use it directly (pre-encoded).

    Handles both forms of the token value:
        "bWM4dm5GT1..."              — raw base64 only
        "Basic bWM4dm5GT1..."        — full header value (strips the prefix)
    """
    token = getattr(settings, "PAYHERO_BASIC_AUTH_TOKEN", "").strip()
    if token:
        # Strip "Basic " prefix if the user pasted the full header value
        if token.lower().startswith("basic "):
            token = token[6:].strip()
        return {"Authorization": f"Basic {token}"}

    username = getattr(settings, "PAYHERO_USERNAME", "")
    password = getattr(settings, "PAYHERO_PASSWORD", "")
    if not username or not password:
        raise ValueError("PayHero credentials not configured. Set PAYHERO_USERNAME and PAYHERO_PASSWORD.")

    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    h.update(_auth_header())
    return h


# ── Result shapes ─────────────────────────────────────────────────────────────

@dataclass
class StkPushResult:
    success: bool
    # PayHero's reference — used later for status checks
    payhero_reference: str = ""
    # Checkout request ID from M-Pesa (informational)
    checkout_request_id: str = ""
    error: str = ""


@dataclass
class StatusResult:
    # Normalised status: "success" | "failed" | "cancelled" | "queued" | "unknown"
    status: str
    mpesa_receipt: str = ""
    result_description: str = ""
    error: str = ""


# ── Phone normalisation ───────────────────────────────────────────────────────

def normalise_phone(raw: str) -> str:
    """
    Convert any common KE phone format to E.164 without the leading +.

    Accepted inputs:
        0712345678      → 254712345678   (leading zero)
        +254712345678   → 254712345678   (full E.164 with +)
        254712345678    → 254712345678   (already E.164 without +)
        712345678       → 254712345678   (9-digit local, no prefix — from split UI input)
        0712 345 678    → 254712345678   (spaces/dashes stripped)
    """
    phone = raw.strip().replace(" ", "").replace("-", "")
    # Strip leading +
    if phone.startswith("+"):
        phone = phone[1:]
    # Leading 0 → replace with country code
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    # Bare 9-digit number (no country code, no leading zero) — e.g. 712345678
    if len(phone) == 9 and not phone.startswith("254"):
        phone = "254" + phone
    return phone


# ── STK Push ─────────────────────────────────────────────────────────────────

def initiate_stk_push(
    *,
    amount: int,
    phone: str,
    external_reference: str,
    callback_url: str,
    customer_name: str = "",
) -> StkPushResult:
    """
    Initiate an M-Pesa STK Push via PayHero.

    POST https://backend.payhero.co.ke/api/v2/payments
    Body: amount, phone_number, channel_id, provider, external_reference,
          customer_name, callback_url
    Returns 201 with { success, status:"QUEUED", reference, CheckoutRequestID }
    """
    channel_id = getattr(settings, "PAYHERO_CHANNEL_ID", "")
    if not channel_id:
        return StkPushResult(success=False, error="PAYHERO_CHANNEL_ID not configured.")

    normalised = normalise_phone(phone)

    payload = {
        "amount": amount,
        "phone_number": normalised,
        "channel_id": int(channel_id),
        "provider": "m-pesa",
        "external_reference": external_reference,
        "customer_name": customer_name or "Customer",
        "callback_url": callback_url,
    }

    try:
        response = requests.post(
            f"{PAYHERO_API_BASE}/payments",
            json=payload,
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        logger.error("PayHero STK push timed out for ref=%s", external_reference)
        return StkPushResult(success=False, error="Request timed out.")
    except requests.ConnectionError as exc:
        logger.error("PayHero STK push connection error for ref=%s: %s", external_reference, exc)
        return StkPushResult(success=False, error=f"Connection error: {exc}")
    except requests.RequestException as exc:
        logger.error("PayHero STK push failed for ref=%s: %s", external_reference, exc)
        return StkPushResult(success=False, error=str(exc))

    if response.status_code == 201:
        body = response.json()
        return StkPushResult(
            success=True,
            payhero_reference=body.get("reference", ""),
            checkout_request_id=body.get("CheckoutRequestID", ""),
        )

    # Non-201 — extract error details without exposing credentials
    try:
        body = response.json()
        description = body.get("message") or body.get("detail") or response.text[:300]
    except Exception:
        description = response.text[:300]

    logger.error(
        "PayHero STK push HTTP %s for ref=%s: %s",
        response.status_code, external_reference, description,
    )
    return StkPushResult(
        success=False,
        error=f"PayHero returned HTTP {response.status_code}: {description}",
    )


# ── Transaction status check ─────────────────────────────────────────────────

def check_transaction_status(reference: str) -> StatusResult:
    """
    Query PayHero for the current status of a transaction.

    GET https://backend.payhero.co.ke/api/v2/transaction-status?reference=<ref>
    Returns { status, success, reference, provider_reference,
              third_party_reference, CheckoutRequestID, … }
    Status values: QUEUED | SUCCESS | FAILED
    """
    try:
        response = requests.get(
            f"{PAYHERO_API_BASE}/transaction-status",
            params={"reference": reference},
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        logger.error("PayHero status check timed out for ref=%s", reference)
        return StatusResult(status="unknown", error="Request timed out.")
    except requests.RequestException as exc:
        logger.error("PayHero status check failed for ref=%s: %s", reference, exc)
        return StatusResult(status="unknown", error=str(exc))

    if not response.ok:
        logger.error("PayHero status check HTTP %s for ref=%s", response.status_code, reference)
        return StatusResult(status="unknown", error=f"HTTP {response.status_code}")

    body = response.json()
    raw_status = (body.get("status") or "").upper()

    status_map = {
        "SUCCESS": "success",
        "FAILED": "failed",
        "QUEUED": "queued",
    }
    normalised = status_map.get(raw_status, "unknown")

    return StatusResult(
        status=normalised,
        mpesa_receipt=body.get("provider_reference", "") or body.get("third_party_reference", ""),
        result_description=body.get("ResultDesc", ""),
    )


# ── Callback parser ───────────────────────────────────────────────────────────

@dataclass
class CallbackResult:
    external_reference: str
    status: str           # "success" | "failed" | "cancelled"
    mpesa_receipt: str
    result_code: Optional[int]
    result_description: str
    amount: Optional[int]
    phone: str


def parse_callback(body: dict) -> Optional[CallbackResult]:
    """
    Parse a PayHero callback POST body into a normalised CallbackResult.

    PayHero callback shape:
    {
      "forward_url": "...",
      "status": "SUCCESS" | "FAILED" | "CANCELLED",
      "response": {
        "Amount": 150,
        "CheckoutRequestID": "...",
        "ExternalReference": "WH-...",
        "MerchantRequestID": "...",
        "MpesaReceiptNumber": "...",
        "Phone": "254...",
        "ResultCode": 0,
        "ResultDesc": "The service request is processed successfully.",
        "Status": "SUCCESS"
      }
    }
    ResultCode 0 → paid. Any other value → not paid.
    Returns None if the body is malformed.
    """
    try:
        resp = body.get("response", {})
        raw_status = (body.get("status") or resp.get("Status") or "").upper()

        result_code = resp.get("ResultCode")
        # Treat ResultCode 0 as definitive success, regardless of status string
        if result_code == 0:
            status = "success"
        elif raw_status in ("FAILED", "CANCELLED"):
            status = raw_status.lower()
        else:
            status = "failed"

        external_reference = resp.get("ExternalReference", "")
        if not external_reference:
            logger.warning("PayHero callback missing ExternalReference: %s", body)
            return None

        return CallbackResult(
            external_reference=external_reference,
            status=status,
            mpesa_receipt=resp.get("MpesaReceiptNumber", ""),
            result_code=result_code,
            result_description=resp.get("ResultDesc", ""),
            amount=resp.get("Amount"),
            phone=resp.get("Phone", ""),
        )
    except Exception as exc:
        logger.error("Failed to parse PayHero callback: %s | body: %s", exc, body)
        return None
