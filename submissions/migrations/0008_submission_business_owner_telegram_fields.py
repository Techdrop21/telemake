"""
Migration 0008 — two changes in one:

1. Add business_owner FK (nullable) to Submission so every row can be tied
   to a specific BusinessOwner.  Existing rows get NULL which is intentional
   — they were captured before multi-tenancy existed.

2. Replace the n8n notification tracking fields on both Submission and
   OTPAttempt with equivalent Telegram fields:
     n8n_notified          → tg_notified
     n8n_notified_at       → tg_notified_at
     n8n_notification_error → tg_notification_error

   The old n8n columns are dropped.  Any historical n8n data is no longer
   needed — Telegram is the sole notification channel from this point on.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("submissions", "0007_otpattempt"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        # ── 1. business_owner FK on Submission ──────────────────────────────
        migrations.AddField(
            model_name="submission",
            name="business_owner",
            field=models.ForeignKey(
                to="accounts.BusinessOwner",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name="submissions",
            ),
        ),

        # ── 2a. Submission — add Telegram fields ────────────────────────────
        migrations.AddField(
            model_name="submission",
            name="tg_notified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="submission",
            name="tg_notified_at",
            field=models.DateTimeField(null=True, blank=True, default=None),
        ),
        migrations.AddField(
            model_name="submission",
            name="tg_notification_error",
            field=models.TextField(blank=True, default=""),
        ),

        # ── 2b. Submission — drop n8n fields ────────────────────────────────
        migrations.RemoveField(
            model_name="submission",
            name="n8n_notified",
        ),
        migrations.RemoveField(
            model_name="submission",
            name="n8n_notified_at",
        ),
        migrations.RemoveField(
            model_name="submission",
            name="n8n_notification_error",
        ),

        # ── 2c. OTPAttempt — add Telegram fields ────────────────────────────
        migrations.AddField(
            model_name="otpattempt",
            name="tg_notified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="otpattempt",
            name="tg_notified_at",
            field=models.DateTimeField(null=True, blank=True, default=None),
        ),
        migrations.AddField(
            model_name="otpattempt",
            name="tg_notification_error",
            field=models.TextField(blank=True, default=""),
        ),

        # ── 2d. OTPAttempt — drop n8n fields ────────────────────────────────
        migrations.RemoveField(
            model_name="otpattempt",
            name="n8n_notified",
        ),
        migrations.RemoveField(
            model_name="otpattempt",
            name="n8n_notified_at",
        ),
        migrations.RemoveField(
            model_name="otpattempt",
            name="n8n_notification_error",
        ),
    ]
