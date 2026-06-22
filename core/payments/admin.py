from django.contrib import admin
from django.urls import path, reverse
from django.http import HttpResponseRedirect
import jdatetime
from django.utils import timezone

from .models import Counterparty, CustomerOrder, CustomerOrderItem, CustomerOrderLog, CustomerSalesAssignment, FieldRequirementConfig, InvoiceExtractionJob, InvoiceRecord, LoginAdvertisement, LoginRecord, PaymentActivityLog, PaymentRecord, PaymentReceipt, ProductCatalog, ProfileChangeRequest, ReconciliationMessage, ReconciliationMessageLog, ReconciliationMessageReadReceipt, ReconciliationReadState, ReconciliationThread, SystemActivityLog, SystemSettings, UploadSettings, UserProfile, WarrantyClaim, WarrantyClaimFile, WarrantyClaimLog


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
        'is_locked',
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
    list_display = ('user', 'first_name', 'last_name', 'role', 'login_lock_status', 'multi_session_override', 'suspended')
    list_filter = ('role', 'city', 'province', 'force_password_change', 'suspended', 'multi_session_override')
    search_fields = ('user__username', 'user__email', 'phone', 'mobile', 'second_mobile', 'representative_name', 'representative_mobile', 'organization', 'first_name', 'last_name')
    readonly_fields = ('user',)
    actions = ['unlock_login', 'allow_multi_session', 'deny_multi_session', 'reset_multi_session']
    fieldsets = (
        ('اطلاعات کاربر', {
            'fields': ('user', 'first_name', 'last_name', 'phone', 'mobile', 'second_mobile', 'representative_name', 'representative_mobile', 'delegate_sms_to_representative', 'organization', 'avatar_image', 'avatar_preset')
        }),
        ('اطلاعات تماس', {
            'fields': ('city', 'province', 'address', 'second_address')
        }),
        ('اطلاعات حساب', {
            'fields': ('role', 'active_from', 'valid_until', 'force_password_change', 'suspended', 'accounting_code')
        }),
        ('تنظیمات امنیتی', {
            'fields': ('multi_session_override',),
            'description': 'خالی = پیروی از تنظیم سراسری | فعال = همیشه مجاز | غیرفعال = همیشه ممنوع',
        }),
    )

    def login_lock_status(self, obj):
        try:
            from axes.models import AccessAttempt
            from django.conf import settings as dj_settings
            from django.utils import timezone as tz
            cooloff = getattr(dj_settings, 'AXES_COOLOFF_TIME', None)
            limit = getattr(dj_settings, 'AXES_FAILURE_LIMIT', 5)
            qs = AccessAttempt.objects.filter(username=obj.user.username)
            if cooloff:
                qs = qs.filter(attempt_time__gte=tz.now() - cooloff)
            if qs.filter(failures_since_start__gte=limit).exists():
                return '🔒 قفل'
            return '✅ آزاد'
        except Exception:
            return '—'
    login_lock_status.short_description = 'وضعیت ورود'

    @admin.action(description='🔓 آزادسازی از قفل ورود')
    def unlock_login(self, request, queryset):
        from axes.models import AccessAttempt
        count = 0
        for profile in queryset:
            deleted, _ = AccessAttempt.objects.filter(username=profile.user.username).delete()
            if deleted:
                count += 1
        self.message_user(request, f'قفل ورود {count} کاربر برداشته شد.')

    @admin.action(description='✅ مجاز به ورود از چند دستگاه')
    def allow_multi_session(self, request, queryset):
        queryset.update(multi_session_override=True)
        self.message_user(request, f'{queryset.count()} کاربر: ورود از چند دستگاه مجاز شد.')

    @admin.action(description='🚫 ممنوع از ورود از چند دستگاه')
    def deny_multi_session(self, request, queryset):
        queryset.update(multi_session_override=False)
        self.message_user(request, f'{queryset.count()} کاربر: ورود از چند دستگاه ممنوع شد.')

    @admin.action(description='↩ بازگشت به تنظیم سراسری (چند دستگاه)')
    def reset_multi_session(self, request, queryset):
        queryset.update(multi_session_override=None)
        self.message_user(request, f'{queryset.count()} کاربر: تنظیم چند دستگاه به حالت سراسری بازگشت.')

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
    list_display = ('name', 'get_status_badge', 'get_linked_user', 'description', 'jalali_updated_at')
    list_filter = ('status',)
    search_fields = ('name', 'user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)
    fieldsets = (
        ('اطلاعات طرف حساب', {'fields': ('name', 'description')}),
        ('حساب کاربری و وضعیت', {
            'fields': ('user', 'status'),
            'description': (
                '⚠ تنظیم وضعیت: '
                'فعال = ورود و عملیات مجاز | '
                'غیرفعال = ورود مجاز، تایید ممنوع | '
                'معلق = ورود ممنوع (حساب کاربری به‌صورت خودکار غیرفعال می‌شود)'
            ),
        }),
    )

    def get_status_badge(self, obj):
        colors = {
            'active':    '#16a34a',
            'inactive':  '#d97706',
            'suspended': '#dc2626',
        }
        labels = {
            'active':    '✅ فعال',
            'inactive':  '⚠ غیرفعال',
            'suspended': '🔴 معلق',
        }
        color = colors.get(obj.status, '#64748b')
        label = labels.get(obj.status, obj.status)
        from django.utils.html import format_html
        return format_html(
            '<span style="color:{};font-weight:700;">{}</span>',
            color, label,
        )
    get_status_badge.short_description = 'وضعیت'

    def get_linked_user(self, obj):
        if obj.user:
            active = '✓' if obj.user.is_active else '✗'
            return f'{active} {obj.user.get_full_name() or obj.user.username} ({obj.user.username})'
        return '—'
    get_linked_user.short_description = 'حساب کاربری'

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


@admin.register(LoginRecord)
class LoginRecordAdmin(admin.ModelAdmin):
    list_display = (
        'jalali_login_at', 'user', 'ip_address',
        'browser_family', 'browser_version',
        'os_family', 'os_version',
        'device_type', 'device_brand',
        'accept_language',
        'jalali_logout_at', 'logout_reason',
    )
    list_filter = ('device_type', 'logout_reason', 'login_at', 'os_family', 'browser_family')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ip_address', 'x_forwarded_for')
    readonly_fields = (
        'user', 'session_key', 'ip_address', 'x_forwarded_for',
        'user_agent_raw', 'browser_family', 'browser_version',
        'os_family', 'os_version', 'device_type', 'device_brand', 'device_model',
        'accept_language', 'jalali_login_at', 'jalali_logout_at', 'logout_reason',
    )
    date_hierarchy = 'login_at'
    ordering = ('-login_at',)

    def jalali_login_at(self, obj):
        return format_jalali_datetime(obj.login_at)

    def jalali_logout_at(self, obj):
        return format_jalali_datetime(obj.logout_at) if obj.logout_at else '-'

    jalali_login_at.short_description = 'زمان ورود'
    jalali_logout_at.short_description = 'زمان خروج'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


from .models import UserSession


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'username', 'role', 'ip_address', 'jalali_last_activity', 'jalali_login_at', 'device_info')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ip_address')
    list_filter = ('user__profile__role',)
    actions = ['force_logout']
    ordering = ('-last_activity_at',)

    def get_queryset(self, request):
        from django.contrib.sessions.models import Session
        valid_keys = Session.objects.filter(
            expire_date__gt=timezone.now()
        ).values_list('session_key', flat=True)
        return super().get_queryset(request).select_related(
            'user', 'user__profile'
        ).filter(session_key__in=valid_keys)

    def display_name(self, obj):
        return obj.user.profile.display_name if hasattr(obj.user, 'profile') else obj.user.username
    display_name.short_description = 'نام کاربر'

    def username(self, obj):
        return obj.user.username
    username.short_description = 'نام کاربری'

    def role(self, obj):
        return obj.user.profile.get_role_display() if hasattr(obj.user, 'profile') else '—'
    role.short_description = 'نقش'

    def jalali_last_activity(self, obj):
        return format_jalali_datetime(obj.last_activity_at) if obj.last_activity_at else '—'
    jalali_last_activity.short_description = 'آخرین فعالیت'

    def jalali_login_at(self, obj):
        rec = obj.user.login_records.filter(session_key=obj.session_key).first()
        return format_jalali_datetime(rec.login_at) if rec else '—'
    jalali_login_at.short_description = 'زمان ورود'

    def device_info(self, obj):
        rec = obj.user.login_records.filter(session_key=obj.session_key).first()
        if not rec:
            return '—'
        parts = [rec.browser_family, rec.os_family]
        return ' / '.join(p for p in parts if p) or '—'
    device_info.short_description = 'مرورگر / سیستم‌عامل'

    @admin.action(description='⏏ اخراج از سیستم')
    def force_logout(self, request, queryset):
        from django.contrib.sessions.models import Session
        from django.utils import timezone as _tz
        count = 0
        for us in queryset:
            Session.objects.filter(session_key=us.session_key).delete()
            LoginRecord.objects.filter(
                user=us.user, session_key=us.session_key, logout_at__isnull=True
            ).update(logout_at=_tz.now(), logout_reason=LoginRecord.LOGOUT_FORCED)
            us.delete()
            count += 1
        self.message_user(request, f'{count} کاربر از سیستم خارج شدند.')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


class LockedUserProxy(UserSession):
    class Meta:
        proxy = True
        verbose_name = 'کاربر قفل‌شده'
        verbose_name_plural = 'کاربران قفل‌شده (axes)'


@admin.register(LockedUserProxy)
class LockedUserAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'username', 'role', 'locked_ip', 'failures', 'jalali_locked_at', 'unlock_remaining')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    actions = ['unlock_users']

    def get_queryset(self, request):
        from axes.models import AccessAttempt
        from django.conf import settings as dj_settings
        from django.utils import timezone as _tz
        cooloff = getattr(dj_settings, 'AXES_COOLOFF_TIME', None)
        limit = getattr(dj_settings, 'AXES_FAILURE_LIMIT', 5)
        locked_usernames = AccessAttempt.objects.filter(failures_since_start__gte=limit)
        if cooloff:
            locked_usernames = locked_usernames.filter(attempt_time__gte=_tz.now() - cooloff)
        locked_set = set(locked_usernames.values_list('username', flat=True))
        return super().get_queryset(request).select_related('user', 'user__profile').filter(
            user__username__in=locked_set
        )

    def _get_attempt(self, obj):
        from axes.models import AccessAttempt
        return AccessAttempt.objects.filter(username=obj.user.username).order_by('-attempt_time').first()

    def display_name(self, obj):
        return obj.user.profile.display_name if hasattr(obj.user, 'profile') else obj.user.username
    display_name.short_description = 'نام کاربر'

    def username(self, obj):
        return obj.user.username
    username.short_description = 'نام کاربری'

    def role(self, obj):
        return obj.user.profile.get_role_display() if hasattr(obj.user, 'profile') else '—'
    role.short_description = 'نقش'

    def locked_ip(self, obj):
        a = self._get_attempt(obj)
        return a.ip_address if a else '—'
    locked_ip.short_description = 'آدرس IP'

    def failures(self, obj):
        a = self._get_attempt(obj)
        return f"{a.failures_since_start} بار" if a else '—'
    failures.short_description = 'تعداد تلاش'

    def jalali_locked_at(self, obj):
        a = self._get_attempt(obj)
        return format_jalali_datetime(a.attempt_time) if a else '—'
    jalali_locked_at.short_description = 'زمان قفل'

    def unlock_remaining(self, obj):
        from axes.models import AccessAttempt
        from django.conf import settings as dj_settings
        from django.utils import timezone as _tz
        cooloff = getattr(dj_settings, 'AXES_COOLOFF_TIME', None)
        if not cooloff:
            return 'دائمی'
        a = self._get_attempt(obj)
        if not a:
            return '—'
        unlock_at = a.attempt_time + cooloff
        remaining = unlock_at - _tz.now()
        if remaining.total_seconds() <= 0:
            return 'آزاد شده'
        mins = int(remaining.total_seconds() // 60)
        return f'{mins} دقیقه دیگر'
    unlock_remaining.short_description = 'زمان تا آزادسازی خودکار'

    @admin.action(description='🔓 آزادسازی از قفل')
    def unlock_users(self, request, queryset):
        from axes.models import AccessAttempt
        count = 0
        for us in queryset:
            deleted, _ = AccessAttempt.objects.filter(username=us.user.username).delete()
            if deleted:
                count += 1
        self.message_user(request, f'قفل {count} کاربر برداشته شد.')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FieldRequirementConfig)
class FieldRequirementConfigAdmin(admin.ModelAdmin):
    list_display = (
        'get_form_display', 'field_label', 'field_name',
        'get_default_display', 'get_override_display', 'get_effective_display',
    )
    list_filter = ('form_name', 'is_required', 'default_required')
    ordering = ('form_name', 'field_label')
    readonly_fields = ('form_name', 'field_name', 'field_label', 'default_required')
    fields = ('form_name', 'field_name', 'field_label', 'default_required', 'is_required')

    def get_form_display(self, obj):
        return obj.get_form_name_display()
    get_form_display.short_description = 'فرم'

    def get_default_display(self, obj):
        return '✅ اجباری' if obj.default_required else '⬜ اختیاری'
    get_default_display.short_description = 'پیشفرض کد'

    def get_override_display(self, obj):
        if obj.is_required is None:
            return '— (پیشفرض)'
        return '✅ اجباری' if obj.is_required else '⬜ اختیاری'
    get_override_display.short_description = 'تنظیم ادمین'

    def get_effective_display(self, obj):
        eff = obj.effective_required
        return ('✅ اجباری' if eff else '⬜ اختیاری')
    get_effective_display.short_description = 'مقدار فعلی'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ('session_inactivity_timeout', 'sms_provider', 'sms_notifications_enabled', 'jalali_updated_at')
    fieldsets = (
        ('تنظیمات نشست', {
            'fields': ('session_inactivity_timeout', 'allow_multiple_sessions'),
            'description': 'مقادیر زیر حداکثر ۶۰ ثانیه پس از ذخیره اعمال می‌شوند.',
        }),
        ('تنظیمات منو', {
            'fields': ('customer_warranty_menu_enabled',),
        }),
        ('تنظیمات پیامک', {
            'fields': (
                'sms_provider',
                'sms_api_key',
                'sms_sender',
                'sms_notifications_enabled',
            ),
            'description': 'برای فعال‌سازی پیامک، اپراتور را انتخاب و API Key را وارد کنید.',
        }),
        ('تنظیمات پیشرفته پیامک', {
            'classes': ('collapse',),
            'fields': (
                'sms_otp_template',
                'sms_otp_expiry_minutes',
                'sms_generic_url',
                'sms_generic_extra',
            ),
        }),
        ('تنظیمات Jitsi Meet', {
            'fields': ('jitsi_call_enabled', 'jitsi_server_url'),
            'description': 'برای فعال‌سازی تماس صوتی، ابتدا آدرس سرور را وارد کنید سپس نمایش دکمه را فعال نمایید.',
        }),
    )

    def jalali_updated_at(self, obj):
        return format_jalali_datetime(obj.updated_at)

    jalali_updated_at.short_description = 'آخرین بروزرسانی'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser and not SystemSettings.objects.exists()

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
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


@admin.register(ProductCatalog)
class ProductCatalogAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'product_code', 'unit', 'coefficient', 'is_active', 'jalali_created_at')
    list_filter = ('is_active',)
    list_editable = ('is_active',)
    search_fields = ('product_name', 'product_code')
    change_list_template = 'admin/payments/productcatalog/change_list.html'

    def jalali_created_at(self, obj):
        return format_jalali_datetime(obj.created_at)
    jalali_created_at.short_description = 'زمان ثبت'

    def get_urls(self):
        custom = [
            path('import-excel/', self.admin_site.admin_view(self._import_excel), name='productcatalog_import_excel'),
        ]
        return custom + super().get_urls()

    def _import_excel(self, request):
        from django.urls import reverse as _rev
        return HttpResponseRedirect(_rev('import_product_catalog'))

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


class ReconciliationMessageInline(admin.TabularInline):
    model = ReconciliationMessage
    extra = 0
    readonly_fields = ('sender', 'body', 'is_edited', 'is_deleted', 'deleted_by', 'document_type', 'document_id', 'created_at')
    can_delete = False


@admin.register(ReconciliationThread)
class ReconciliationThreadAdmin(admin.ModelAdmin):
    list_display = ('title', 'customer', 'status', 'is_internal', 'document_type', 'document_id', 'created_by', 'updated_at')
    list_filter = ('status', 'is_internal', 'document_type', 'created_at', 'updated_at')
    search_fields = ('title', 'customer__username', 'customer__first_name', 'customer__last_name')
    filter_horizontal = ('staff_participants',)
    inlines = [ReconciliationMessageInline]


@admin.register(ReconciliationMessage)
class ReconciliationMessageAdmin(admin.ModelAdmin):
    list_display = ('thread', 'sender', 'is_edited', 'is_deleted', 'deleted_by', 'created_at')
    list_filter = ('is_deleted', 'is_edited', 'is_internal', 'created_at', 'document_type')
    search_fields = ('body', 'thread__title', 'sender__username')
    readonly_fields = ('created_at', 'edited_at', 'deleted_at', 'deleted_by', 'is_edited', 'is_deleted')


@admin.register(ReconciliationMessageLog)
class ReconciliationMessageLogAdmin(admin.ModelAdmin):
    list_display = ('message', 'action', 'actor', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('message__thread__title', 'actor__username')
    readonly_fields = ('message', 'actor', 'action', 'old_body', 'timestamp')


@admin.register(ReconciliationMessageReadReceipt)
class ReconciliationMessageReadReceiptAdmin(admin.ModelAdmin):
    list_display = ('message', 'user', 'read_at')
    list_filter = ('read_at',)
    search_fields = ('message__thread__title', 'user__username')
    readonly_fields = ('message', 'user', 'read_at')


@admin.register(ReconciliationReadState)
class ReconciliationReadStateAdmin(admin.ModelAdmin):
    list_display = ('thread', 'user', 'last_read_at')
    list_filter = ('last_read_at',)
    search_fields = ('thread__title', 'user__username')


class WarrantyClaimFileInline(admin.TabularInline):
    model = WarrantyClaimFile
    extra = 0
    readonly_fields = ('uploaded_by', 'uploaded_at')


class WarrantyClaimLogInline(admin.TabularInline):
    model = WarrantyClaimLog
    extra = 0
    readonly_fields = ('actor', 'action', 'note', 'is_visible_to_customer', 'created_at')
    can_delete = False


@admin.register(WarrantyClaim)
class WarrantyClaimAdmin(admin.ModelAdmin):
    list_display = ('tracking_code', 'claimant_name', 'claimant_phone', 'part_name', 'serial_number', 'status', 'priority', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('tracking_code', 'claimant_name', 'claimant_phone', 'serial_number', 'part_name')
    readonly_fields = ('tracking_code', 'created_at', 'updated_at', 'reviewed_at', 'resolved_at')
    inlines = [WarrantyClaimFileInline, WarrantyClaimLogInline]
    date_hierarchy = 'created_at'


@admin.register(WarrantyClaimFile)
class WarrantyClaimFileAdmin(admin.ModelAdmin):
    list_display = ('claim', 'description', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('claim__tracking_code', 'description')


@admin.register(WarrantyClaimLog)
class WarrantyClaimLogAdmin(admin.ModelAdmin):
    list_display = ('claim', 'actor', 'action', 'is_visible_to_customer', 'created_at')
    list_filter = ('action', 'is_visible_to_customer', 'created_at')
    search_fields = ('claim__tracking_code', 'note', 'actor__username')
