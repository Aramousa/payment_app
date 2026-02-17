import hashlib

from django import forms
from django.core.exceptions import ValidationError
from django_jalali.forms import jDateField, jDateInput
from django.utils.safestring import mark_safe

from .models import Counterparty, PaymentRecord


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            if not data:
                return []
            cleaned_files = []
            errors = []
            for uploaded in data:
                try:
                    cleaned_files.append(super().clean(uploaded, initial))
                except ValidationError as exc:
                    errors.extend(exc.error_list)
            if errors:
                raise ValidationError(errors)
            return cleaned_files
        if not data:
            return []
        return [super().clean(data, initial)]


class PaymentRecordForm(forms.ModelForm):
    ACCOUNT_FIELDS = ('first_name', 'last_name', 'organization', 'city', 'phone')
    OPTIONAL_PAYER_FIELDS = (
        'payer_account_number',
        'payer_first_name',
        'payer_last_name',
        'payer_bank_name',
        'payer_bank_branch',
    )
    receipt_images = MultiFileField(
        required=False,
        widget=MultiFileInput(attrs={'multiple': True}),
        label='تصاویر فیش',
    )

    pay_date = jDateField(
        label='تاریخ',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d')
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._receipt_payload = []
        self.fields['tracking_code'].required = True

        for field_name in self.ACCOUNT_FIELDS:
            field = self.fields[field_name]
            field.disabled = True
            css_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css_class + ' readonly-field').strip()

        # Do not show placeholder Z in editable form fields.
        for name in self.OPTIONAL_PAYER_FIELDS:
            if self.initial.get(name) == 'Z':
                self.initial[name] = ''
            if self.instance and getattr(self.instance, name, '') == 'Z' and not self.is_bound:
                self.initial[name] = ''

        # Show required marker for mandatory fields in UI.
        for name, field in self.fields.items():
            if field.required and not field.disabled and name != 'receipt_images':
                field.label = mark_safe(f'{field.label} <span style=\"color:#d00;\">*</span>')

    class Meta:
        model = PaymentRecord
        fields = [
            'first_name',
            'last_name',
            'organization',
            'city',
            'phone',
            'payer_account_number',
            'payer_first_name',
            'payer_last_name',
            'payer_bank_name',
            'payer_bank_branch',
            'amount',
            'tracking_code',
            'pay_date',
        ]
        widgets = {
            'first_name': forms.TextInput(),
            'last_name': forms.TextInput(),
            'organization': forms.TextInput(),
            'city': forms.TextInput(),
            'phone': forms.TextInput(),
            'payer_account_number': forms.TextInput(),
            'payer_first_name': forms.TextInput(),
            'payer_last_name': forms.TextInput(),
            'payer_bank_name': forms.TextInput(),
            'payer_bank_branch': forms.TextInput(),
            'amount': forms.TextInput(attrs={'class': 'amount-input'}),
            'pay_date': jDateInput(format='%Y/%m/%d', attrs={'class': 'jalali-date'}),
        }

        labels = {
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'organization': 'مجموعه',
            'city': 'شهر',
            'phone': 'شماره تلفن',
            'payer_account_number': 'شماره حساب واریز کننده',
            'payer_first_name': 'نام واریز کننده',
            'payer_last_name': 'نام خانوادگی واریز کننده',
            'payer_bank_name': 'نام بانک',
            'payer_bank_branch': 'شعبه',
            'amount': 'مبلغ',
            'tracking_code': 'کد پیگیری',
            'pay_date': 'تاریخ',
            'receipt_images': 'تصاویر فیش',
        }

    def clean_receipt_images(self):
        files = self.files.getlist('receipt_images')

        if not self.instance.pk and not files:
            raise ValidationError('حداقل یک تصویر فیش لازم است.')

        existing_hashes = set()
        if self.instance.pk:
            existing_hashes = set(self.instance.receipts.values_list('file_hash', flat=True))

        payload = []
        seen_hashes = set()

        for uploaded in files:
            digest = hashlib.sha256()
            for chunk in uploaded.chunks():
                digest.update(chunk)
            file_hash = digest.hexdigest()
            uploaded.seek(0)

            if file_hash in seen_hashes or file_hash in existing_hashes:
                raise ValidationError('تصاویر تکراری برای این رکورد مجاز نیست.')

            seen_hashes.add(file_hash)
            payload.append((uploaded, file_hash))

        self._receipt_payload = payload
        return files

    def receipt_payload(self):
        return self._receipt_payload


class StaffStatusUpdateForm(forms.Form):
    status = forms.ChoiceField(
        choices=PaymentRecord.STATUS_CHOICES,
        label='وضعیت جدید',
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        label='توضیحات',
    )
    counterparty = forms.ModelChoiceField(
        queryset=Counterparty.objects.all(),
        required=False,
        label='طرف حساب',
    )


class CounterpartyForm(forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = ['name', 'description']
        labels = {
            'name': 'طرف حساب',
            'description': 'توضیحات',
        }
