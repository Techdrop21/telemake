"""
Migration 0002

1. Alter Subscription.plan choices — adds 'weekly' and 'biannual', keeps
   'monthly'. Old values 'quarterly' and 'annual' are dropped from choices
   but any existing rows with those values are safe (Django stores the raw
   string, not an integer code).

2. Add Subscription.days_remaining helper fields are computed, no schema
   change needed for those.

3. Add the Payment model — tracks every STK push attempt independently.
"""

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # ── 1. Update Subscription plan field choices ────────────────────────
        migrations.AlterField(
            model_name="subscription",
            name="plan",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("weekly", "Weekly"),
                    ("monthly", "Monthly"),
                    ("biannual", "6 Months"),
                ],
                default="weekly",
            ),
        ),

        # ── 2. Add Payment model ─────────────────────────────────────────────
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "business_owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payments",
                        to="accounts.businessowner",
                    ),
                ),
                ("plan", models.CharField(max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("phone", models.CharField(max_length=20)),
                ("external_reference", models.CharField(max_length=100, unique=True)),
                ("payhero_reference", models.CharField(blank=True, default="", max_length=255)),
                ("mpesa_receipt", models.CharField(blank=True, default="", max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("queued", "Queued"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("stale", "Stale"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("result_description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
