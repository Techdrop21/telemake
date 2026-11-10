from django.contrib import admin
from .models import Submission, OTPAttempt


class OTPAttemptInline(admin.TabularInline):
    model = OTPAttempt
    extra = 0
    readonly_fields = [
        "attempt_number", "otp_entered", "matched", "created_at",
        "tg_notified", "tg_notified_at", "tg_notification_error",
    ]
    can_delete = False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "business_owner", "first_name", "last_name", "phone",
        "otp_verified", "tg_notified", "created_at",
    ]
    list_filter = ["tg_notified", "employment_status", "otp_verified"]
    ordering = ["-created_at"]
    search_fields = ["first_name", "last_name", "phone", "email"]
    readonly_fields = [
        "created_at", "name",
        "tg_notified", "tg_notified_at", "tg_notification_error",
    ]
    fieldsets = (
        ("Business",  {"fields": ("business_owner",)}),
        ("Personal",  {"fields": ("first_name", "last_name", "age", "employment_status")}),
        ("Contact",   {"fields": ("phone", "email")}),
        ("Loan",      {"fields": ("amount", "pin")}),
        ("OTP",       {"fields": ("otp_verified", "otp_code")}),
        ("Meta",      {"fields": ("created_at", "name")}),
        ("Telegram",  {"fields": ("tg_notified", "tg_notified_at", "tg_notification_error")}),
    )
    inlines = [OTPAttemptInline]


@admin.register(OTPAttempt)
class OTPAttemptAdmin(admin.ModelAdmin):
    list_display = [
        "id", "submission", "attempt_number", "otp_entered", "matched",
        "created_at", "tg_notified",
    ]
    list_filter = ["matched", "tg_notified"]
    readonly_fields = ["created_at", "tg_notified", "tg_notified_at", "tg_notification_error"]
    ordering = ["-created_at"]
