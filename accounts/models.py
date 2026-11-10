import uuid
from datetime import timedelta
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ── Plan catalogue ────────────────────────────────────────────────────────────
# Single source of truth for pricing and durations.
# Change prices here and they propagate everywhere.

PLAN_CATALOGUE = {
    "weekly": {
        "label": "Weekly",
        "price": Decimal("1.00"),
        "duration_days": 7,
        "currency": "KES",
    },
    "monthly": {
        "label": "Monthly",
        "price": Decimal("490.00"),
        "duration_days": 30,
        "currency": "KES",
        # saves vs 4 × weekly
        "saves": Decimal("150.00") * 4 - Decimal("490.00"),
    },
    "biannual": {
        "label": "6 Months",
        "price": Decimal("2250.00"),
        "duration_days": 180,
        "currency": "KES",
        # saves vs 6 × monthly
        "saves": Decimal("490.00") * 6 - Decimal("2250.00"),
    },
}


class BusinessOwner(models.Model):
    """
    Extends Django's User model with business-specific fields.
    Each business owner gets a unique public UUID for their form URLs.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="business_profile")
    public_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    business_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.user.email})"

    def get_public_form_url(self):
        """Returns the public form URL path for this business owner."""
        return f"/f/{self.public_uuid}/"


class TelegramConfiguration(models.Model):
    """
    Telegram bot configuration for each business owner.
    Credentials are stored here and used to send notifications.
    """
    business_owner = models.OneToOneField(
        BusinessOwner,
        on_delete=models.CASCADE,
        related_name="telegram_config"
    )
    bot_token = models.CharField(max_length=255, help_text="Telegram Bot API token")
    chat_id = models.CharField(max_length=100, help_text="Telegram chat ID where notifications are sent")
    is_active = models.BooleanField(default=True, help_text="Whether this configuration is active")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram Configuration"
        verbose_name_plural = "Telegram Configurations"

    def __str__(self):
        return f"Telegram config for {self.business_owner.business_name}"


class Subscription(models.Model):
    """
    One subscription record per business owner (OneToOne).
    Status and expiry are updated by the payment callback handler.
    """
    STATUS_CHOICES = [
        ("inactive", "Inactive"),
        ("pending", "Pending"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ]

    PLAN_CHOICES = [
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("biannual", "6 Months"),
    ]

    business_owner = models.OneToOneField(
        BusinessOwner,
        on_delete=models.CASCADE,
        related_name="subscription"
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="weekly")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="inactive")
    # Amount paid for the current active period (KES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_reference = models.CharField(max_length=255, blank=True, default="")
    start_date = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_owner.business_name} — {self.get_plan_display()} ({self.status})"

    def is_active(self):
        """Return True only when status is active AND expiry has not passed."""
        if self.status != "active":
            return False
        if self.expiry_date and self.expiry_date < timezone.now():
            return False
        return True

    def days_remaining(self):
        """Days left in the current period, or 0 if expired/inactive."""
        if not self.is_active() or not self.expiry_date:
            return 0
        delta = self.expiry_date - timezone.now()
        return max(0, delta.days)

    def activate(self, plan_key: str, payment_reference: str, amount: Decimal):
        """
        Activate or extend this subscription after a confirmed payment.
        If already active, extends from the current expiry_date so renewals
        stack rather than overwriting remaining time.
        """
        from accounts.models import PLAN_CATALOGUE  # local import avoids circularity
        plan_info = PLAN_CATALOGUE[plan_key]
        days = plan_info["duration_days"]

        now = timezone.now()
        # Extend from expiry if still active, otherwise start fresh from now
        base = self.expiry_date if (self.is_active() and self.expiry_date and self.expiry_date > now) else now

        self.plan = plan_key
        self.status = "active"
        self.amount = amount
        self.payment_reference = payment_reference
        self.start_date = now
        self.expiry_date = base + timedelta(days=days)
        self.save()


class Payment(models.Model):
    """
    One row per payment attempt — including failures and pending ones.
    The subscription is only updated when status reaches SUCCESS.
    Idempotency is enforced by external_reference (unique per attempt).
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("queued", "Queued"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("stale", "Stale"),
    ]

    business_owner = models.ForeignKey(
        BusinessOwner,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    plan = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Phone number the STK push was sent to (E.164, e.g. 254712345678)
    phone = models.CharField(max_length=20)

    # Our unique reference — sent to PayHero, matched in callback
    external_reference = models.CharField(max_length=100, unique=True)

    # PayHero's own reference (returned on initiation, used for status checks)
    payhero_reference = models.CharField(max_length=255, blank=True, default="")
    # M-Pesa receipt number (from callback when SUCCESS)
    mpesa_receipt = models.CharField(max_length=100, blank=True, default="")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    result_description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.external_reference} — {self.status}"

    @staticmethod
    def generate_reference(business_owner_id: int) -> str:
        """Generate a unique external reference in the format WH-<date>-<short-uuid>."""
        date_str = timezone.now().strftime("%y%m%d")
        short = uuid.uuid4().hex[:6].upper()
        return f"WH-{date_str}-{short}-{business_owner_id}"
