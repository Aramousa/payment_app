from django.contrib import admin

from .models import Counterparty, LoginAdvertisement, PaymentActivityLog, PaymentRecord, PaymentReceipt, UserProfile


class PaymentReceiptInline(admin.TabularInline):
    model = PaymentReceipt
    extra = 0
    readonly_fields = ('file_hash', 'created_at')


class PaymentActivityInline(admin.TabularInline):
    model = PaymentActivityLog
    extra = 0
    readonly_fields = ('actor', 'action', 'from_status', 'to_status', 'note', 'created_at')
    can_delete = False


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = (
        'first_name',
        'last_name',
        'payer_full_name',
        'payer_account_number',
        'payer_bank_name',
        'beneficiary_bank_name',
        'beneficiary_account_number',
        'beneficiary_account_owner',
        'formatted_amount',
        'status',
        'locked_by_finance',
        'pay_date',
        'city',
        'counterparty',
    )
    list_filter = ('status', 'city', 'counterparty')
    search_fields = (
        'first_name',
        'last_name',
        'payer_full_name',
        'payer_account_number',
        'payer_bank_name',
        'beneficiary_bank_name',
        'beneficiary_account_number',
        'beneficiary_account_owner',
        'phone',
        'tracking_code',
    )
    inlines = [PaymentReceiptInline, PaymentActivityInline]

    def formatted_amount(self, obj):
        return '{:,}'.format(obj.amount)

    formatted_amount.short_description = 'مبلغ (ریال)'


@admin.register(LoginAdvertisement)
class LoginAdvertisementAdmin(admin.ModelAdmin):
    list_display = ('slot', 'title', 'start_date', 'end_date', 'is_visible', 'updated_at')
    list_filter = ('is_visible', 'start_date', 'end_date')
    search_fields = ('title', 'description', 'link_url')
    ordering = ('slot',)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'organization', 'city', 'role', 'force_password_change')
    list_filter = ('role', 'city', 'force_password_change')
    search_fields = ('user__username', 'phone')


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name',)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentActivityLog)
class PaymentActivityLogAdmin(admin.ModelAdmin):
    list_display = ('payment', 'actor', 'action', 'from_status', 'to_status', 'created_at')
    list_filter = ('action', 'to_status', 'created_at')
    search_fields = ('payment__first_name', 'payment__last_name', 'note', 'actor__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
