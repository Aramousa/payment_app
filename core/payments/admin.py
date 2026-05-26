from django.contrib import admin
import jdatetime
from django.utils import timezone

from .models import Counterparty, CustomerOrder, CustomerOrderItem, CustomerOrderLog, CustomerSalesAssignment, InvoiceExtractionJob, InvoiceRecord, LoginAdvertisement, PaymentActivityLog, PaymentRecord, PaymentReceipt, ProfileChangeRequest, SystemActivityLog, UploadSettings, UserProfile


def format_jalali_datetime(value):
    if not value:
        return '-'
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return jdatetime.datetime.fromgregorian(datetime=value).strftime('%Y/%m/%d %H:%M')


class PaymentReceiptInline(admin.TabularInline):
    model = PaymentReceipt
    extra = 0
    readonly_fields = ('file_hash', 'jalali_created_at')

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    jalali_created_at.short_description = 'تاریخ ثبت'


class PaymentActivityInline(admin.TabularInline):
    model = PaymentActivityLog
    extra = 0
    readonly_fields = ('actor', 'action', 'from_status', 'to_status', 'note', 'jalali_created_at')
    can_delete = False

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    jalali_created_at.short_description = 'تاریخ ثبت'


class CustomerOrderItemInline(admin.TabularInline):
    model = CustomerOrderItem
    extra = 0


class CustomerOrderLogInline(admin.TabularInline):
    model = CustomerOrderLog
    extra = 0
    readonly_fields = ('actor', 'action', 'from_status', 'to_status', 'note', 'jalali_created_at')
    can_delete = False

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    jalali_created_at.short_description = 'تاریخ ثبت'


@admin.register(CustomerOrder)
class CustomerOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'sales_expert', 'status', 'jalali_created_at')
    list_filter = ('status', 'sales_expert', 'created_at')
    search_fields = ('customer__username', 'customer__first_name', 'customer__last_name', 'customer__profile__organization', 'title', 'items__product_name')
    inlines = [CustomerOrderItemInline, CustomerOrderLogInline]

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    jalali_created_at.short_description = 'زمان ثبت'


@admin.register(CustomerSalesAssignment)
class CustomerSalesAssignmentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'sales_user', 'assigned_by', 'jalali_updated_at')
    list_filter = ('sales_user', 'updated_at')
    search_fields = ('customer__username', 'customer__first_name', 'customer__last_name', 'sales_user__username')

    def jalali_updated_at(self, obj):
        return format_jalali_datetime(obj.updated_at)

    jalali_updated_at.short_description = 'آخرین بروزرسانی'


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

    def get_inline_instances(self, request, obj=None):
        if not request.user.is_superuser:
            return [
                inline
                for inline in super().get_inline_instances(request, obj)
                if not isinstance(inline, PaymentActivityInline)
            ]
        return super().get_inline_instances(request, obj)

    def formatted_amount(self, obj):
        return '{:,}'.format(obj.amount)

    formatted_amount.short_description = 'مبلغ (ریال)'


@admin.register(LoginAdvertisement)
class LoginAdvertisementAdmin(admin.ModelAdmin):
    list_display = ('slot', 'title', 'start_date', 'end_date', 'is_visible', 'jalali_updated_at')
    list_filter = ('is_visible', 'start_date', 'end_date')
    search_fields = ('title', 'description', 'link_url')
    ordering = ('slot',)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def jalali_updated_at(self, obj):
        return format_jalali_datetime(obj.updated_at)

    jalali_updated_at.short_description = 'آخرین بروزرسانی'

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(UploadSettings)
class UploadSettingsAdmin(admin.ModelAdmin):
    list_display = ('receipt_max_upload_size_mb', 'invoice_max_upload_size_mb', 'jalali_updated_at')

    def jalali_updated_at(self, obj):
        return format_jalali_datetime(obj.updated_at)

    jalali_updated_at.short_description = 'آخرین بروزرسانی'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser and not UploadSettings.objects.exists()

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'phone', 'mobile', 'second_mobile', 'organization', 'city', 'province', 'role', 'active_from', 'valid_until', 'force_password_change', 'suspended')
    list_filter = ('role', 'city', 'province', 'force_password_change', 'suspended')
    search_fields = ('user__username', 'user__email', 'phone', 'mobile', 'second_mobile', 'organization', 'first_name', 'last_name')
    readonly_fields = ('user',)
    fieldsets = (
        ('اطلاعات کاربر', {
            'fields': ('user', 'first_name', 'last_name', 'phone', 'mobile', 'second_mobile', 'organization')
        }),
        ('اطلاعات تماس', {
            'fields': ('city', 'province', 'address', 'second_address')
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


@admin.register(ProfileChangeRequest)
class ProfileChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'requested_by', 'reviewed_by', 'created_at', 'reviewed_at')
    list_filter = ('status', 'created_at', 'reviewed_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'requested_by__username')
    readonly_fields = ('user', 'requested_by', 'reviewed_by', 'changes', 'status', 'review_note', 'created_at', 'reviewed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'jalali_created_at', 'jalali_updated_at')
    search_fields = ('name',)

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    def jalali_updated_at(self, obj):
        return format_jalali_datetime(obj.updated_at)

    jalali_created_at.short_description = 'تاریخ ثبت'
    jalali_updated_at.short_description = 'آخرین بروزرسانی'

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentActivityLog)
class PaymentActivityLogAdmin(admin.ModelAdmin):
    list_display = ('payment', 'actor', 'action', 'from_status', 'to_status', 'jalali_created_at')
    list_filter = ('action', 'to_status', 'created_at')
    search_fields = ('payment__first_name', 'payment__last_name', 'note', 'actor__username')

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    jalali_created_at.short_description = 'تاریخ ثبت'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(InvoiceRecord)
class InvoiceRecordAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'customer', 'formatted_amount', 'invoice_date', 'uploaded_by', 'jalali_customer_seen_at', 'jalali_created_at')
    list_filter = ('invoice_date', 'created_at', 'customer_seen_at')
    search_fields = ('reference_number', 'customer__username', 'customer__first_name', 'customer__last_name', 'customer__profile__organization')

    def jalali_customer_seen_at(self, obj):
        return format_jalali_datetime(obj.customer_seen_at)

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    def formatted_amount(self, obj):
        if obj.amount is None:
            return '-'
        return '{:,}'.format(obj.amount)

    jalali_customer_seen_at.short_description = 'زمان مشاهده مشتری'
    jalali_created_at.short_description = 'زمان ثبت'
    formatted_amount.short_description = 'مبلغ (ریال)'


@admin.register(InvoiceExtractionJob)
class InvoiceExtractionJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_filename', 'source', 'file_kind', 'text_source', 'status', 'requested_by', 'jalali_created_at', 'jalali_finished_at')
    list_filter = ('status', 'source', 'file_kind', 'text_source', 'created_at')
    search_fields = ('original_filename', 'requested_by__username', 'invoice__reference_number', 'error_message')
    readonly_fields = (
        'invoice',
        'requested_by',
        'source',
        'file',
        'original_filename',
        'file_kind',
        'text_source',
        'status',
        'result_json',
        'raw_text',
        'warnings',
        'error_message',
        'jalali_created_at',
        'jalali_started_at',
        'jalali_finished_at',
    )

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    def jalali_started_at(self, obj):
        return format_jalali_datetime(obj.started_at)

    def jalali_finished_at(self, obj):
        return format_jalali_datetime(obj.finished_at)

    jalali_created_at.short_description = 'زمان ایجاد'
    jalali_started_at.short_description = 'زمان شروع'
    jalali_finished_at.short_description = 'زمان پایان'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SystemActivityLog)
class SystemActivityLogAdmin(admin.ModelAdmin):
    list_display = ('jalali_created_at', 'actor', 'target_user', 'action', 'description')
    list_filter = ('action', 'created_at')
    search_fields = ('actor__username', 'target_user__username', 'description')
    readonly_fields = ('actor', 'target_user', 'action', 'description', 'jalali_created_at')

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)

    jalali_created_at.short_description = 'زمان ثبت'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
