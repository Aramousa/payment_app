from django.contrib import admin
from .models import PaymentRecord

@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'amount', 'status', 'pay_date')
    list_filter = ('status', 'city')
    search_fields = ('first_name', 'last_name', 'phone')
    def formatted_amount(self, obj):
        return "{:,}".format(obj.amount)
    formatted_amount.short_description = 'مبلغ'