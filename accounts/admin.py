from django.contrib import admin
from .models import BusinessOwner, TelegramConfiguration, Subscription, Payment


@admin.register(BusinessOwner)
class BusinessOwnerAdmin(admin.ModelAdmin):
    list_display = [
        "id", "business_name", "user_email", "public_uuid", "phone", "created_at",
    ]
    list_filter = ["created_at"]
    search_fields = ["business_name", "user__email", "public_uuid"]
    readonly_fields = ["public_uuid", "created_at", "updated_at"]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"


@admin.register(TelegramConfiguration)
class TelegramConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "business_owner", "chat_id", "is_active", "created_at", "updated_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["business_owner__business_name", "chat_id"]
    readonly_fields = ["created_at", "updated_at"]
    # bot_token is intentionally excluded from list_display — never show tokens in list views


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "business_owner", "plan", "status",
        "amount", "start_date", "expiry_date", "days_remaining_display",
    ]
    list_filter = ["plan", "status"]
    search_fields = ["business_owner__business_name", "payment_reference"]
    readonly_fields = ["created_at", "updated_at"]

    def days_remaining_display(self, obj):
        return obj.days_remaining() if obj.is_active() else "—"
    days_remaining_display.short_description = "Days left"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id", "business_owner", "plan", "amount", "phone",
        "status", "mpesa_receipt", "external_reference", "created_at",
    ]
    list_filter = ["status", "plan", "created_at"]
    search_fields = [
        "business_owner__business_name", "external_reference",
        "payhero_reference", "mpesa_receipt", "phone",
    ]
    readonly_fields = [
        "external_reference", "payhero_reference", "mpesa_receipt",
        "created_at", "updated_at", "completed_at",
    ]
    ordering = ["-created_at"]

    # Prevent accidental edits to completed payments
    def has_change_permission(self, request, obj=None):
        if obj and obj.status == "success":
            return False
        return super().has_change_permission(request, obj)
