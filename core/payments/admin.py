from django.contrib import admin
from .models import PaymentRecord, UserProfile


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = (
        'first_name',
        'last_name',
        'formatted_amount',
        'status',
        'pay_date',
        'city',
    )
    list_filter = ('status', 'city')
    search_fields = ('first_name', 'last_name', 'phone')

    def formatted_amount(self, obj):
        return "{:,}".format(obj.amount)
    formatted_amount.short_description = 'مبلغ'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'organization', 'city', 'role')
    list_filter = ('role', 'city')
    search_fields = ('user__username', 'phone')
