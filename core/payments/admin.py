from django.contrib import admin

from .models import Counterparty, InvoiceRecord, LoginAdvertisement, PaymentActivityLog, PaymentRecord, PaymentReceipt, UserProfile


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
    list_display = ('user', 'first_name', 'last_name', 'phone', 'mobile', 'organization', 'city', 'province', 'role', 'active_from', 'valid_until', 'force_password_change', 'suspended')
    list_filter = ('role', 'city', 'province', 'force_password_change', 'suspended')
    search_fields = ('user__username', 'phone', 'mobile', 'organization', 'first_name', 'last_name')
    readonly_fields = ('user',)
    fieldsets = (
        ('اطلاعات کاربر', {
            'fields': ('user', 'first_name', 'last_name', 'phone', 'mobile', 'organization')
        }),
        ('اطلاعات تماس', {
            'fields': ('city', 'province', 'address')
        }),
        ('اطلاعات حساب', {
            'fields': ('role', 'active_from', 'valid_until', 'force_password_change', 'suspended')
        }),
    )

    def has_add_permission(self, request):
        # Only superusers can add new user profiles
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # Only superusers can change user profiles
        if obj is None:
            return request.user.is_superuser
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        # Make all fields readonly except for superuser
        if request.user.is_superuser:
            return self.readonly_fields
        return [f.name for f in self.model._meta.get_fields()]

    def get_fieldsets(self, request, obj=None):
        # Only superuser can see all fields
        if request.user.is_superuser:
            return self.fieldsets
        return ()

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Only allow superusers to access the change form
        if not request.user.is_superuser:
            from django.http import Http403Forbidden
            raise Http403Forbidden("شما دسترسی به مدیریت کاربران ندارید.")
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        # Only allow superusers to see the list
        if not request.user.is_superuser:
            from django.http import Http403Forbidden
            raise Http403Forbidden("شما دسترسی به مدیریت کاربران ندارید.")
        return super().changelist_view(request, extra_context)


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


@admin.register(InvoiceRecord)
class InvoiceRecordAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'customer', 'amount', 'invoice_date', 'uploaded_by', 'customer_seen_at', 'created_at')
    list_filter = ('invoice_date', 'created_at', 'customer_seen_at')
    search_fields = ('reference_number', 'customer__username', 'customer__first_name', 'customer__last_name', 'customer__profile__organization')
