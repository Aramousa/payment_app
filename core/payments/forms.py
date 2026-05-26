import hashlib
from io import BytesIO
import os
import random
import re

from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.utils import timezone
from django.utils.safestring import mark_safe
from django_jalali.forms import jDateField, jDateInput
from PIL import Image, ImageOps

from .models import Counterparty, DailyPaymentAssignment, DailyPaymentPlan, InvoiceRecord, PaymentRecord, PriceList, ProformaInvoice, UploadSettings, UserProfile

STAFF_ROLES = {'staff', 'finance', 'commercial', 'sales', 'data_entry'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff'}
DEFAULT_RECEIPT_MAX_UPLOAD_SIZE = 1 * 1024 * 1024
DEFAULT_INVOICE_MAX_UPLOAD_SIZE = 5 * 1024 * 1024
IMAGE_RESIZE_MAX_SIDE = 2200
DATE_INPUT_AUTOCOMPLETE_ATTRS = {
    'autocomplete': 'off',
    'autocorrect': 'off',
    'autocapitalize': 'off',
    'spellcheck': 'false',
    'data-lpignore': 'true',
    'data-form-type': 'other',
}


def _date_input_attrs(**extra):
    attrs = {'class': 'jalali-date', **DATE_INPUT_AUTOCOMPLETE_ATTRS}
    attrs.update(extra)
    return attrs


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(file, initial) for file in files if file]


def _size_label(max_size_bytes):
    mb = max_size_bytes / (1024 * 1024)
    if mb.is_integer():
        return f'{int(mb)} مگابایت'
    return f'{mb:.1f} مگابایت'


def _upload_settings():
    try:
        return UploadSettings.load()
    except Exception:
        return None


def _active_customer_profiles():
    return UserProfile.objects.filter(
        role='customer',
        user__is_active=True,
        suspended=False,
    ).select_related('user').order_by('user__first_name', 'user__last_name', 'user__username')


def _receipt_max_upload_size():
    settings = _upload_settings()
    return settings.receipt_max_upload_size_bytes if settings else DEFAULT_RECEIPT_MAX_UPLOAD_SIZE


def _invoice_max_upload_size():
    settings = _upload_settings()
    return settings.invoice_max_upload_size_bytes if settings else DEFAULT_INVOICE_MAX_UPLOAD_SIZE


def _optimized_image_name(name):
    base = os.path.splitext(os.path.basename(name or 'upload'))[0] or 'upload'
    return f'{base}.jpg'


def _flatten_for_jpeg(image):
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        canvas = Image.new('RGB', image.size, (255, 255, 255))
        alpha = image.convert('RGBA').getchannel('A')
        canvas.paste(image.convert('RGB'), mask=alpha)
        return canvas
    if image.mode != 'RGB':
        return image.convert('RGB')
    return image


def _optimize_uploaded_image(uploaded, max_size_bytes, max_side=IMAGE_RESIZE_MAX_SIDE):
    if not uploaded.size or uploaded.size <= max_size_bytes:
        return uploaded

    try:
        uploaded.seek(0)
        image = Image.open(uploaded)
        image = ImageOps.exif_transpose(image)
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        image = _flatten_for_jpeg(image)
    except Exception:
        try:
            uploaded.seek(0)
        except Exception:
            pass
        return uploaded

    quality = 92
    while True:
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
        if output.tell() <= max_size_bytes:
            output.seek(0)
            return SimpleUploadedFile(
                _optimized_image_name(uploaded.name),
                output.getvalue(),
                content_type='image/jpeg',
            )

        width, height = image.size
        if quality > 78:
            quality -= 4
            continue
        if max(width, height) <= 900:
            break

        image = image.resize((max(1, int(width * 0.9)), max(1, int(height * 0.9))), Image.Resampling.LANCZOS)
        quality = 84

    try:
        uploaded.seek(0)
    except Exception:
        pass
    return uploaded


class BankNameAutocompleteWidget(forms.TextInput):
    """
    Custom widget for bank name autocomplete field.
    """
    
    def __init__(self, attrs=None, bank_type='payer'):
        super().__init__(attrs)
        self.bank_type = bank_type
        if self.attrs is None:
            self.attrs = {}
        
        # Add classes and data attributes
        css_class = self.attrs.get('class', '')
        self.attrs['class'] = (css_class + ' bank-autocomplete-input').strip()
        self.attrs['data-bank-type'] = bank_type
        self.attrs['autocomplete'] = 'off'



class CustomPasswordChangeForm(PasswordChangeForm):
    error_messages = {
        **PasswordChangeForm.error_messages,
        'password_incorrect': 'رمز عبور فعلی اشتباه وارد شده است. لطفاً دوباره وارد کنید.',
        'password_mismatch': 'رمز عبور جدید و تکرار آن یکسان نیستند.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'رمز عبور فعلی'
        self.fields['new_password1'].label = 'رمز عبور جدید'
        self.fields['new_password2'].label = 'تکرار رمز عبور جدید'
        self.fields['new_password1'].help_text = mark_safe(
            'رمز عبور باید حداقل ۵ کاراکتر باشد، فقط شامل حروف انگلیسی و عدد باشد، '
            'و از حداقل دو نوع کاراکتر شامل حرف کوچک، حرف بزرگ یا عدد تشکیل شود.'
            '<br>نمونه صحیح: Ab123، ali12، Test5'
            '<br>نمونه غلط: 1234، abcde، رمز۱۲۳، ab@12'
        )
        self.fields['new_password2'].help_text = 'برای اطمینان، رمز عبور جدید را دوباره وارد کنید.'
        for field in self.fields.values():
            field.error_messages['required'] = 'تکمیل این فیلد الزامی است.'

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1') or ''
        if len(password) < 5:
            raise ValidationError('رمز عبور باید حداقل ۵ کاراکتر باشد.')
        if not re.match(r'^[A-Za-z0-9]+$', password):
            raise ValidationError('رمز عبور باید فقط شامل حروف انگلیسی و اعداد باشد.')
        categories = sum(bool(re.search(pattern, password)) for pattern in [r'[a-z]', r'[A-Z]', r'[0-9]'])
        if categories < 2:
            raise ValidationError('رمز عبور باید ترکیبی از حداقل دو حالت از حروف کوچک، حروف بزرگ و اعداد باشد.')
        return password

    def clean(self):
        self.validate_passwords('new_password1', 'new_password2')
        return forms.Form.clean(self)


class CustomerProfileUpdateForm(forms.ModelForm):
    email = forms.EmailField(label='ایمیل', required=False)

    class Meta:
        model = UserProfile
        fields = ['phone', 'second_mobile', 'organization', 'address', 'second_address']
        widgets = {
            'phone': forms.TextInput(attrs={'inputmode': 'tel'}),
            'second_mobile': forms.TextInput(attrs={'inputmode': 'tel'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'second_address': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'phone': 'شماره تلفن',
            'second_mobile': 'شماره همراه دوم',
            'organization': 'نام مجموعه',
            'address': 'آدرس',
            'second_address': 'آدرس دوم',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.initial['email'] = self.user.email
        for field in self.fields.values():
            field.required = False

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip()

    def changed_profile_fields(self):
        labels = {
            'email': 'ایمیل',
            'phone': 'شماره تلفن',
            'second_mobile': 'شماره همراه دوم',
            'organization': 'نام مجموعه',
            'address': 'آدرس',
            'second_address': 'آدرس دوم',
        }
        changes = []
        for field_name in self.changed_data:
            if field_name not in labels:
                continue
            if field_name == 'email':
                old_value = self.user.email or ''
            else:
                old_value = getattr(self.instance, field_name, '') or ''
            new_value = self.cleaned_data.get(field_name) or ''
            changes.append({
                'name': field_name,
                'field': labels[field_name],
                'old': old_value or '-',
                'new': new_value or '-',
            })
        return changes

    def changes_payload(self):
        return {
            item['name']: {
                'old': '' if item['old'] == '-' else item['old'],
                'new': '' if item['new'] == '-' else item['new'],
            }
            for item in self.changed_profile_fields()
        }


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
    ALLOWED_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.pdf',
    }
    ACCOUNT_FIELDS = ()
    REQUIRED_CUSTOMER_FIELDS = (
        'payer_account_number',
        'payer_full_name',
        'payer_bank_name',
        'beneficiary_bank_name',
        'beneficiary_account_number',
        'beneficiary_account_owner',
        'amount',
        'tracking_code',
        'pay_date',
    )

    receipt_images = MultiFileField(
        required=False,
        widget=MultiFileInput(attrs={
            'multiple': True,
            'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
        }),
        label='فایل های فیش',
        help_text='فقط فایل های تصویر استاندارد و PDF مجاز است. حداکثر حجم هر فایل: ۱ مگابایت.',
    )

    pay_date = jDateField(
        label='تاریخ',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31', inputmode='numeric', dir='ltr'))
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._receipt_payload = []
        self.max_upload_size = _receipt_max_upload_size()
        self.fields['receipt_images'].help_text = (
            f'فقط فایل های تصویر استاندارد و PDF مجاز است. حداکثر حجم هر فایل: {_size_label(self.max_upload_size)}. '
            'اگر تصویر بزرگتر باشد، سیستم آن را تا حد امکان بدون افت محسوس کیفیت بهینه می کند.'
        )

        if not self.is_bound:
            amount_initial = self.initial.get('amount')
            if amount_initial is not None:
                try:
                    self.initial['amount'] = '{:,}'.format(int(str(amount_initial).replace(',', '').strip()))
                except (ValueError, TypeError):
                    pass

        for field in self.fields.values():
            field.required = False
            if hasattr(field.widget, 'attrs'):
                field.widget.attrs.pop('required', None)
                field.widget.attrs.pop('aria-required', None)
            if hasattr(field, 'label_suffix'):
                field.label_suffix = ''
        self.fields['customer_notes'].required = False

        has_existing_files = bool(self.instance and self.instance.pk and self.instance.receipts.exists())
        self.fields['receipt_images'].required = not has_existing_files

        for field_name in self.ACCOUNT_FIELDS:
            field = self.fields[field_name]
            field.disabled = True
            css_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css_class + ' readonly-field').strip()

        for name in ('payer_account_number', 'payer_full_name', 'payer_bank_name', 'beneficiary_bank_name'):
            if self.initial.get(name) == 'Z':
                self.initial[name] = ''
            if self.instance and getattr(self.instance, name, '') == 'Z' and not self.is_bound:
                self.initial[name] = ''

        # Ensure bank name fields have autocomplete classes
        for bank_field in ['payer_bank_name', 'beneficiary_bank_name']:
            if bank_field in self.fields:
                css_class = self.fields[bank_field].widget.attrs.get('class', '')
                self.fields[bank_field].widget.attrs['class'] = (css_class + ' bank-autocomplete-input').strip()
                bank_type = 'payer' if bank_field == 'payer_bank_name' else 'beneficiary'
                self.fields[bank_field].widget.attrs['data-bank-type'] = bank_type
                self.fields[bank_field].widget.attrs['autocomplete'] = 'off'

        for name, field in self.fields.items():
            if field.label:
                field.label = re.sub(r'\s*<span[^>]*>\*</span>$', '', str(field.label))

    class Meta:
        model = PaymentRecord
        fields = [
            'payer_account_number',
            'payer_full_name',
            'payer_bank_name',
            'beneficiary_bank_name',
            'beneficiary_account_number',
            'beneficiary_account_owner',
            'amount',
            'tracking_code',
            'pay_date',
            'customer_notes',
        ]
        widgets = {
            'payer_account_number': forms.TextInput(),
            'payer_full_name': forms.TextInput(),
            'payer_bank_name': BankNameAutocompleteWidget(bank_type='payer'),
            'beneficiary_bank_name': BankNameAutocompleteWidget(bank_type='beneficiary'),
            'beneficiary_account_number': forms.TextInput(),
            'beneficiary_account_owner': forms.TextInput(),
            'amount': forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
            'pay_date': jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31', inputmode='numeric', dir='ltr')),
            'customer_notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'اختیاری'}),
        }
        labels = {
            'payer_account_number': 'شماره حساب واریز کننده',
            'payer_full_name': 'نام و نام خانوادگی واریز کننده',
            'payer_bank_name': 'بانک مبدا',
            'beneficiary_bank_name': 'بانک مقصد',
            'beneficiary_account_number': 'شماره حساب مقصد',
            'beneficiary_account_owner': 'نام صاحب حساب مقصد',
            'amount': 'مبلغ (ریال)',
            'tracking_code': 'کد پیگیری',
            'pay_date': 'تاریخ',
            'receipt_images': 'فایل های فیش',
            'customer_notes': 'توضیح',
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None:
            return 0
        if amount <= 0:
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت و به ریال باشد.')
        return amount

    def clean_pay_date(self):
        pay_date = self.cleaned_data.get('pay_date')
        if pay_date is None:
            return timezone.localdate()
        return pay_date

    def clean_receipt_images(self):
        files = self.files.getlist('receipt_images')
        has_existing_files = bool(self.instance.pk and self.instance.receipts.exists())
        if not files and not has_existing_files:
            raise ValidationError('حداقل یک فایل فیش لازم است.')

        existing_hashes = set()
        if self.instance.pk:
            existing_hashes = set(self.instance.receipts.values_list('file_hash', flat=True))

        payload = []
        seen_hashes = set()
        for uploaded in files:
            ext = os.path.splitext(uploaded.name or '')[1].lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationError('فرمت فایل مجاز نیست. فقط تصویرهای استاندارد و PDF پذیرفته می شود.')
            if ext in IMAGE_EXTENSIONS:
                uploaded = _optimize_uploaded_image(uploaded, self.max_upload_size)
            if uploaded.size and uploaded.size > self.max_upload_size:
                raise ValidationError(f'حجم هر فایل باید حداکثر {_size_label(self.max_upload_size)} باشد.')

            digest = hashlib.sha256()
            for chunk in uploaded.chunks():
                digest.update(chunk)
            file_hash = digest.hexdigest()
            uploaded.seek(0)

            if file_hash in seen_hashes or file_hash in existing_hashes:
                raise ValidationError('فایل تکراری برای این رکورد مجاز نیست.')

            seen_hashes.add(file_hash)
            payload.append((uploaded, file_hash))

        self._receipt_payload = payload
        return [uploaded for uploaded, _file_hash in payload]

    def receipt_payload(self):
        return self._receipt_payload


class StaffPaymentDetailsForm(forms.ModelForm):
    pay_date = jDateField(
        label='تاریخ',
        required=False,
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31', inputmode='numeric', dir='ltr')),
    )

    class Meta:
        model = PaymentRecord
        fields = [
            'payer_account_number',
            'payer_full_name',
            'payer_bank_name',
            'beneficiary_bank_name',
            'beneficiary_account_number',
            'beneficiary_account_owner',
            'amount',
            'tracking_code',
            'pay_date',
        ]
        widgets = {
            'payer_account_number': forms.TextInput(),
            'payer_full_name': forms.TextInput(),
            'payer_bank_name': BankNameAutocompleteWidget(bank_type='payer'),
            'beneficiary_bank_name': BankNameAutocompleteWidget(bank_type='beneficiary'),
            'beneficiary_account_number': forms.TextInput(),
            'beneficiary_account_owner': forms.TextInput(),
            'amount': forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
            'pay_date': jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31', inputmode='numeric', dir='ltr')),
        }
        labels = {
            'payer_account_number': 'شماره حساب واریز کننده',
            'payer_full_name': 'نام و نام خانوادگی واریز کننده',
            'payer_bank_name': 'بانک مبدا',
            'beneficiary_bank_name': 'بانک مقصد',
            'beneficiary_account_number': 'شماره حساب مقصد',
            'beneficiary_account_owner': 'نام صاحب حساب مقصد',
            'amount': 'مبلغ (ریال)',
            'tracking_code': 'کد پیگیری',
            'pay_date': 'تاریخ',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.initial.get('amount') is not None:
            try:
                self.initial['amount'] = '{:,}'.format(int(str(self.initial['amount']).replace(',', '').strip()))
            except (ValueError, TypeError):
                pass
        for bank_field in ['payer_bank_name', 'beneficiary_bank_name']:
            css_class = self.fields[bank_field].widget.attrs.get('class', '')
            self.fields[bank_field].widget.attrs['class'] = (css_class + ' bank-autocomplete-input').strip()
            self.fields[bank_field].widget.attrs['data-bank-type'] = 'payer' if bank_field == 'payer_bank_name' else 'beneficiary'
            self.fields[bank_field].widget.attrs['autocomplete'] = 'off'

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None:
            return 0
        if amount <= 0:
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت و به ریال باشد.')
        return amount


class StaffStatusUpdateForm(forms.Form):
    status = forms.ChoiceField(
        choices=PaymentRecord.STATUS_CHOICES,
        label='وضعیت جدید',
    )
    note = forms.CharField(
        required=False,
        label='توضیح',
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    counterparty = forms.ModelChoiceField(
        queryset=Counterparty.objects.all(),
        required=False,
        label='طرف حساب',
        empty_label='بدون طرف حساب',
    )


class DailyPaymentPlanForm(forms.ModelForm):
    total_expected_amount = forms.CharField(
        label='مبلغ کل مورد انتظار',
        widget=forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
    )
    deposit_date = jDateField(
        label='تاریخ واریز',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31', inputmode='numeric', dir='ltr')),
    )

    class Meta:
        model = DailyPaymentPlan
        fields = ['deposit_date', 'bank_name', 'account_number', 'account_owner', 'total_expected_amount', 'note']
        widgets = {
            'bank_name': BankNameAutocompleteWidget(bank_type='beneficiary'),
            'account_number': forms.TextInput(attrs={'dir': 'ltr'}),
            'account_owner': forms.TextInput(),
            'note': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'bank_name': 'نام بانک',
            'account_number': 'شماره حساب مقصد',
            'account_owner': 'نام صاحب حساب',
            'note': 'توضیح',
        }

    def clean_total_expected_amount(self):
        raw_amount = str(self.cleaned_data.get('total_expected_amount') or '').replace(',', '').strip()
        if not raw_amount.isdigit():
            raise ValidationError('مبلغ کل باید یک عدد صحیح مثبت باشد.')
        amount = int(raw_amount)
        if amount <= 0:
            raise ValidationError('مبلغ کل باید یک عدد صحیح مثبت باشد.')
        return amount


class DailyPaymentAssignmentForm(forms.ModelForm):
    expected_amount = forms.CharField(
        label='مبلغ مورد انتظار مشتری',
        widget=forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
    )
    customers = forms.ModelMultipleChoiceField(
        queryset=UserProfile.objects.none(),
        label='مشتریان',
        widget=forms.SelectMultiple(attrs={'size': 8, 'data-customer-select': '1'}),
    )

    class Meta:
        model = DailyPaymentAssignment
        fields = ['customers', 'expected_amount', 'note']
        widgets = {
            'note': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'note': 'توضیح',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = _active_customer_profiles()
        self.fields['customers'].label_from_instance = self._customer_label

    @staticmethod
    def _customer_label(profile):
        full_name = profile.user.get_full_name().strip() or profile.user.username
        parts = [full_name, profile.user.username]
        if profile.organization:
            parts.append(profile.organization)
        if profile.province:
            parts.append(profile.province)
        if profile.city:
            parts.append(profile.city)
        if profile.phone:
            parts.append(profile.phone)
        return ' | '.join(parts)

    def clean_customers(self):
        profiles = self.cleaned_data['customers']
        if not profiles:
            raise ValidationError('حداقل یک مشتری را انتخاب کنید.')
        return [profile.user for profile in profiles]

    def clean_expected_amount(self):
        raw_amount = str(self.cleaned_data.get('expected_amount') or '').replace(',', '').strip()
        if not raw_amount.isdigit():
            raise ValidationError('مبلغ مشتری باید یک عدد صحیح مثبت باشد.')
        amount = int(raw_amount)
        if amount <= 0:
            raise ValidationError('مبلغ مشتری باید یک عدد صحیح مثبت باشد.')
        return amount
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


class InvoiceUploadForm(forms.ModelForm):
    ALLOWED_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.pdf',
    }

    customer = forms.ModelChoiceField(
        queryset=UserProfile.objects.none(),
        label='مشتری',
        empty_label='انتخاب مشتری',
        required=True,
        widget=forms.Select(attrs={'data-customer-select': '1'}),
    )
    confirm_assignment = forms.BooleanField(
        required=True,
        label='انتساب فاکتور به مشتری انتخاب شده را تایید می کنم.',
    )
    invoice_date = jDateField(
        label='تاریخ فاکتور',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31')),
        required=False,
    )
    amount = forms.CharField(
        label='مبلغ (ریال)',
        widget=forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
        required=False,
    )

    class Meta:
        model = InvoiceRecord
        fields = ['customer', 'invoice_date', 'invoice_number', 'reference_number', 'attachment', 'customer_visible_note', 'internal_note']
        exclude = ['amount']
        widgets = {
            'invoice_number': forms.TextInput(attrs={'dir': 'ltr', 'placeholder': 'شماره فاکتور از سیستم حسابداری'}),
            'reference_number': forms.TextInput(attrs={'dir': 'ltr', 'placeholder': 'اختیاری'}),
            'attachment': forms.ClearableFileInput(attrs={
                'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
            }),
            'customer_visible_note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'متنی که مشتری بتواند ببیند'}),
            'internal_note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'فقط برای مالی و بازرگانی'}),
        }
        labels = {
            'invoice_date': 'تاریخ فاکتور',
            'invoice_number': 'شماره فاکتور',
            'amount': 'مبلغ (ریال)',
            'reference_number': 'شماره حواله',
            'attachment': 'تصویر یا فایل PDF',
            'customer_visible_note': 'توضیحات کارشناس بازرگانی برای مشتری',
            'internal_note': 'توضیحات داخلی',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_upload_size = _invoice_max_upload_size()
        self.fields['attachment'].help_text = (
            f'فقط فایل های تصویری استاندارد و PDF مجاز است. حداکثر حجم فایل: {_size_label(self.max_upload_size)}. '
            'اگر تصویر بزرگتر باشد، سیستم آن را تا حد امکان بدون افت محسوس کیفیت بهینه می کند.'
        )
        if not self.is_bound:
            amount_initial = self.initial.get('amount')
            if amount_initial is not None:
                try:
                    self.initial['amount'] = '{:,}'.format(int(str(amount_initial).replace(',', '').strip()))
                except (ValueError, TypeError):
                    pass

        self.fields['customer'].queryset = _active_customer_profiles()
        self.fields['customer'].label_from_instance = self._customer_label
        
        # فیلدهای ضروری
        self.fields['customer'].required = True
        self.fields['attachment'].required = True
        
        # سایر فیلدها اختیاری
        self.fields['invoice_date'].required = False
        self.fields['invoice_number'].required = False
        self.fields['amount'].required = False
        self.fields['reference_number'].required = False
        self.fields['customer_visible_note'].required = False
        self.fields['internal_note'].required = False
        
        for name, field in self.fields.items():
            if field.required:
                field.label = mark_safe(f'{field.label} <span style="color:#d00;">*</span>')

    @staticmethod
    def _customer_label(profile):
        full_name = profile.user.get_full_name().strip() or profile.user.username
        parts = [full_name, profile.user.username]
        if profile.organization:
            parts.append(profile.organization)
        if profile.province:
            parts.append(profile.province)
        if profile.city:
            parts.append(profile.city)
        if profile.phone:
            parts.append(profile.phone)
        return ' | '.join(parts)

    def clean_customer(self):
        profile = self.cleaned_data['customer']
        if profile.role != 'customer':
            raise ValidationError('فقط کاربران مشتری قابل انتخاب هستند.')
        return profile.user

    def clean_amount(self):
        raw_amount = str(self.cleaned_data.get('amount') or '').replace(',', '').strip()
        if not raw_amount:
            return None  # مبلغ اختیاری است
        if not raw_amount.isdigit():
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت باشد.')
        amount = int(raw_amount)
        if amount <= 0:
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت باشد.')
        return amount

    def clean_invoice_number(self):
        invoice_number = (self.cleaned_data.get('invoice_number') or '').strip()
        # شماره فاکتور اختیاری است
        return invoice_number

    def clean_reference_number(self):
        # Reference number is optional, return empty string if not provided
        return (self.cleaned_data.get('reference_number') or '').strip()

    def clean_attachment(self):
        uploaded = self.cleaned_data.get('attachment')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError('فقط فایل های تصویری استاندارد و PDF مجاز است.')
        if ext in IMAGE_EXTENSIONS:
            uploaded = _optimize_uploaded_image(uploaded, self.max_upload_size)
        if uploaded.size and uploaded.size > self.max_upload_size:
            raise ValidationError(f'حجم فایل باید حداکثر {_size_label(self.max_upload_size)} باشد.')
        return uploaded


class PriceListUploadForm(forms.ModelForm):
    ALLOWED_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.pdf',
    }

    customers = forms.ModelMultipleChoiceField(
        queryset=UserProfile.objects.none(),
        label='مشتریان',
        required=True,
        widget=forms.SelectMultiple(attrs={'size': 8, 'data-customer-select': '1'}),
    )
    files = MultipleFileField(
        label='فایل‌های لیست قیمت',
        required=True,
        widget=MultipleFileInput(attrs={
            'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
            'multiple': True,
        }),
    )

    class Meta:
        model = PriceList
        fields = ['customers', 'title', 'files', 'note']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'مثلا لیست قیمت اردیبهشت'}),
            'note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'فقط برای کارکنان شرکت'}),
        }
        labels = {
            'title': 'عنوان',
            'note': 'توضیحات داخلی',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = _active_customer_profiles()
        self.fields['customers'].label_from_instance = InvoiceUploadForm._customer_label

    def clean_files(self):
        files = self.cleaned_data.get('files') or []
        if not files:
            raise ValidationError('حداقل یک فایل را انتخاب کنید.')
        for uploaded in files:
            ext = os.path.splitext(uploaded.name or '')[1].lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationError('فقط فایل‌های تصویری استاندارد و PDF مجاز است.')
        return files

    def clean_customers(self):
        profiles = self.cleaned_data['customers']
        if not profiles:
            raise ValidationError('حداقل یک مشتری را انتخاب کنید.')
        if any(profile.role != 'customer' for profile in profiles):
            raise ValidationError('فقط کاربران مشتری قابل انتخاب هستند.')
        return [profile.user for profile in profiles]


class ProformaInvoiceForm(forms.ModelForm):
    ALLOWED_EXTENSIONS = PriceListUploadForm.ALLOWED_EXTENSIONS

    customers = forms.ModelMultipleChoiceField(
        queryset=UserProfile.objects.none(),
        label='مشتریان',
        required=True,
        widget=forms.SelectMultiple(attrs={'size': 8, 'data-customer-select': '1'}),
    )
    valid_until = jDateField(
        label='اعتبار تا',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31')),
        required=True,
    )
    files = MultipleFileField(
        label='فایل‌های پیش فاکتور',
        required=True,
        widget=MultipleFileInput(attrs={
            'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
            'multiple': True,
        }),
    )

    class Meta:
        model = ProformaInvoice
        fields = ['customers', 'title', 'valid_until', 'files', 'note']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'مثلا پیش فاکتور اردیبهشت'}),
            'note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'فقط برای کارکنان شرکت'}),
        }
        labels = {
            'title': 'عنوان',
            'note': 'توضیحات داخلی',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = _active_customer_profiles()
        self.fields['customers'].label_from_instance = InvoiceUploadForm._customer_label

    def clean_customers(self):
        profiles = self.cleaned_data['customers']
        if not profiles:
            raise ValidationError('حداقل یک مشتری را انتخاب کنید.')
        if any(profile.role != 'customer' for profile in profiles):
            raise ValidationError('فقط کاربران مشتری قابل انتخاب هستند.')
        return [profile.user for profile in profiles]

    def clean_files(self):
        files = self.cleaned_data.get('files') or []
        if not files:
            raise ValidationError('حداقل یک فایل پیش فاکتور را انتخاب کنید.')
        for uploaded in files:
            ext = os.path.splitext(uploaded.name or '')[1].lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationError('فقط فایل‌های تصویری استاندارد و PDF مجاز است.')
        return files


class InvoiceCustomerNoteForm(forms.ModelForm):
    class Meta:
        model = InvoiceRecord
        fields = ['customer_note']
        widgets = {
            'customer_note': forms.Textarea(attrs={'rows': 4, 'placeholder': 'یادداشت شخصی شما'}),
        }
        labels = {
            'customer_note': 'یادداشت شخصی',
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.customer_note_updated_at = timezone.now()
        if commit:
            instance.save(update_fields=['customer_note', 'customer_note_updated_at'])
        return instance


class UserAccountManagementForm(forms.Form):
    ROLE_CHOICES = (
        ('customer', 'مشتری'),
        ('commercial', 'بازرگانی'),
        ('finance', 'مالی'),
        ('sales', 'فروش'),
        ('data_entry', 'تکمیل اطلاعات فیش'),
        ('staff', 'کارمند'),
    )

    first_name = forms.CharField(label='نام', max_length=50, required=True)
    last_name = forms.CharField(label='نام خانوادگی', max_length=50, required=True)
    phone = forms.CharField(label='شماره تماس', max_length=20, required=False)
    mobile = forms.CharField(label='شماره همراه', max_length=20, required=True)
    province = forms.CharField(label='استان', max_length=50, required=True)
    city = forms.CharField(label='شهر', max_length=50, required=True)
    address = forms.CharField(label='آدرس', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    organization = forms.CharField(label='نام مجموعه', max_length=100, required=True)
    email = forms.EmailField(label='ایمیل', required=False)
    password = forms.CharField(label='کلمه عبور', required=True, widget=forms.TextInput(attrs={'dir': 'ltr', 'inputmode': 'latin'}))
    role = forms.ChoiceField(label='نقش', choices=ROLE_CHOICES)
    active_from = jDateField(
        label='تاریخ آغاز فعالیت',
        required=True,
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31')),
    )
    valid_until = jDateField(
        label='تاریخ اعتبار',
        required=True,
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/12/29')),
    )
    force_password_change = forms.BooleanField(label='الزام تغییر رمز در ورود بعدی', required=False)
    suspended = forms.BooleanField(label='معلق', required=False, initial=False)
    can_view_invoices = forms.BooleanField(label='دسترسی مشاهده فاکتورها', required=False)
    can_upload_invoices = forms.BooleanField(label='دسترسی بارگذاری فاکتورها', required=False)
    can_edit_payment_details = forms.BooleanField(label='دسترسی تکمیل اطلاعات فیش‌ها', required=False)
    is_active = forms.BooleanField(label='فعال', required=False, initial=True)

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.password_suggestion = kwargs.pop('password_suggestion', '')
        super().__init__(*args, **kwargs)

        if self.instance and not self.is_bound:
            profile = getattr(self.instance, 'profile', None)
            self.initial.update({
                'first_name': self.instance.first_name,
                'last_name': self.instance.last_name,
                'phone': getattr(profile, 'phone', ''),
                'mobile': getattr(profile, 'mobile', ''),
                'province': getattr(profile, 'province', ''),
                'city': getattr(profile, 'city', ''),
                'address': getattr(profile, 'address', ''),
                'organization': getattr(profile, 'organization', ''),
                'email': self.instance.email,
                'role': getattr(profile, 'role', 'customer'),
                'active_from': getattr(profile, 'active_from', None),
                'valid_until': getattr(profile, 'valid_until', None),
                'force_password_change': getattr(profile, 'force_password_change', False),
                'suspended': getattr(profile, 'suspended', False),
                'can_view_invoices': getattr(profile, 'can_view_invoices', False),
                'can_upload_invoices': getattr(profile, 'can_upload_invoices', False),
                'can_edit_payment_details': getattr(profile, 'can_edit_payment_details', False),
            })

        for name, field in self.fields.items():
            if name in {'password'}:
                continue
            if field.required:
                field.label = mark_safe(f'{field.label} <span style="color:#d00;">*</span>')

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        mobile = (cleaned_data.get('mobile') or '').strip()
        phone = (cleaned_data.get('phone') or '').strip()

        # Check required fields
        first_name = (cleaned_data.get('first_name') or '').strip()
        last_name = (cleaned_data.get('last_name') or '').strip()
        organization = (cleaned_data.get('organization') or '').strip()
        province = (cleaned_data.get('province') or '').strip()
        city = (cleaned_data.get('city') or '').strip()
        active_from = cleaned_data.get('active_from')
        valid_until = cleaned_data.get('valid_until')
        password = (cleaned_data.get('password') or '').strip()

        if not first_name:
            self.add_error('first_name', 'نام الزامی است.')

        if not last_name:
            self.add_error('last_name', 'نام خانوادگی الزامی است.')

        if not mobile:
            self.add_error('mobile', 'شماره همراه الزامی است.')

        if not organization:
            self.add_error('organization', 'نام مجموعه الزامی است.')

        if not province:
            self.add_error('province', 'استان الزامی است.')

        if not city:
            self.add_error('city', 'شهر الزامی است.')

        if not active_from:
            self.add_error('active_from', 'تاریخ آغاز فعالیت الزامی است.')

        if not valid_until:
            self.add_error('valid_until', 'تاریخ اعتبار الزامی است.')

        if not password and not self.instance:
            self.add_error('password', 'کلمه عبور الزامی است.')

        # username باید برابر mobile باشد
        cleaned_data['username'] = mobile

        # Check if mobile is unique across all users
        if mobile:
            existing_by_mobile = User.objects.filter(username=mobile)
            if self.instance:
                existing_by_mobile = existing_by_mobile.exclude(pk=self.instance.pk)
            if existing_by_mobile.exists():
                raise ValidationError('این شماره موبایل قبلاً برای کاربری دیگر ثبت شده است.')

        # For customers, check for duplicate phone
        if role == 'customer' and phone:

            existing_by_phone = UserProfile.objects.filter(phone=phone, role='customer')
            if self.instance:
                existing_by_phone = existing_by_phone.exclude(user=self.instance)
            if existing_by_phone.exists():
                raise ValidationError('مشتری دیگری با این شماره تماس ثبت شده است.')

        return cleaned_data

    def clean_password(self):
        password = (self.cleaned_data.get('password') or '').strip()
        if not password and not self.instance:
            raise ValidationError('کلمه عبور الزامی است.')
        if password:
            if len(password) < 5:
                raise ValidationError('کلمه عبور باید حداقل ۵ کاراکتر باشد.')
            if not re.match(r'^[A-Za-z0-9]+$', password):
                raise ValidationError('کلمه عبور باید فقط شامل حروف انگلیسی و اعداد باشد.')
            categories = sum(bool(re.search(pattern, password)) for pattern in [r'[a-z]', r'[A-Z]', r'[0-9]'])
            if categories < 2:
                raise ValidationError('کلمه عبور باید ترکیبی از حداقل دو حالت از حروف کوچک، حروف بزرگ و اعداد باشد.')
        return password

    def save(self):
        instance = self.instance or User()
        # username باید برابر mobile باشد
        mobile = (self.cleaned_data.get('mobile') or '').strip()
        instance.username = mobile
        instance.email = self.cleaned_data.get('email', '').strip()
        instance.first_name = self.cleaned_data.get('first_name', '').strip()
        instance.last_name = self.cleaned_data.get('last_name', '').strip()
        instance.is_active = self.cleaned_data.get('is_active', False)
        role = self.cleaned_data.get('role')
        instance.is_staff = instance.is_superuser or role in STAFF_ROLES
        password = self.cleaned_data.get('password', '').strip()
        if password:
            instance.set_password(password)
        instance.save()

        profile = instance.profile
        profile.first_name = (self.cleaned_data.get('first_name') or '').strip()
        profile.last_name = (self.cleaned_data.get('last_name') or '').strip()
        profile.phone = (self.cleaned_data.get('phone') or '').strip()
        profile.mobile = (self.cleaned_data.get('mobile') or '').strip()
        profile.province = (self.cleaned_data.get('province') or '').strip()
        profile.city = (self.cleaned_data.get('city') or '').strip()
        profile.address = (self.cleaned_data.get('address') or '').strip()
        profile.organization = (self.cleaned_data.get('organization') or '').strip()
        profile.role = self.cleaned_data['role']
        profile.active_from = self.cleaned_data.get('active_from')
        profile.valid_until = self.cleaned_data.get('valid_until')
        profile.force_password_change = self.cleaned_data.get('force_password_change', False)
        profile.suspended = self.cleaned_data.get('suspended', False)
        profile.can_view_invoices = self.cleaned_data.get('can_view_invoices', False)
        profile.can_upload_invoices = self.cleaned_data.get('can_upload_invoices', False)
        profile.can_edit_payment_details = self.cleaned_data.get('can_edit_payment_details', False)
        profile.save()
        return instance
