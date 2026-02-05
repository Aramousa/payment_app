from django import forms
from django_jalali.forms import jDateField, jDateInput
from .models import PaymentRecord


class PaymentRecordForm(forms.ModelForm):
    pay_date = jDateField(
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d')
    )

    class Meta:
        model = PaymentRecord
        fields = [
            'first_name',
            'last_name',
            'organization',
            'city',
            'phone',
            'amount',
            'tracking_code',
            'pay_date',
            'receipt_image',
        ]


        labels = {
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'organization': 'مجموعه',
            'city': 'شهر',
            'phone': 'شماره تلفن',
            'amount': 'مبلغ',
            'tracking_code': 'کد پیگیری',
            'pay_date': 'تاریخ واریز',
            'receipt_image': 'سند واریز',
        }
