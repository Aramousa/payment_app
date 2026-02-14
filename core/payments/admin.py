from django.contrib import admin

from .models import Counterparty, PaymentActivityLog, PaymentRecord, PaymentReceipt, UserProfile


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
        'formatted_amount',
        'status',
        'pay_date',
        'city',
        'counterparty',
    )
    list_filter = ('status', 'city', 'counterparty')
    search_fields = ('first_name', 'last_name', 'phone', 'tracking_code')
    inlines = [PaymentReceiptInline, PaymentActivityInline]

    def formatted_amount(self, obj):
        return '{:,}'.format(obj.amount)

    formatted_amount.short_description = 'مبلغ'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'organization', 'city', 'role')
    list_filter = ('role', 'city')
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
