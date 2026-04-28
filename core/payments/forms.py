import hashlib
import os

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.safestring import mark_safe
from django_jalali.forms import jDateField, jDateInput

from .models import Counterparty, InvoiceRecord, PaymentRecord, UserProfile


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
    MAX_UPLOAD_SIZE = 1 * 1024 * 1024
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
        help_text='فقط فایل های تصویر استاندارد و PDF مجاز است. حداکثر حجم هر فایل: 1 مگابایت.',
    )

    pay_date = jDateField(
        label='تاریخ',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs={'class': 'jalali-date', 'placeholder': '1403/01/31', 'inputmode': 'numeric', 'dir': 'ltr'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._receipt_payload = []

        for name in self.REQUIRED_CUSTOMER_FIELDS:
            self.fields[name].required = True

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

        for name, field in self.fields.items():
            if field.required and not field.disabled:
                field.label = mark_safe(f'{field.label} <span style="color:#d00;">*</span>')

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
            'payer_bank_name': forms.TextInput(),
            'beneficiary_bank_name': forms.TextInput(),
            'beneficiary_account_number': forms.TextInput(),
            'beneficiary_account_owner': forms.TextInput(),
            'amount': forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
            'pay_date': jDateInput(format='%Y/%m/%d', attrs={'class': 'jalali-date', 'placeholder': '1403/01/31', 'inputmode': 'numeric', 'dir': 'ltr'}),
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
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت و به ریال باشد.')
        return amount

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
            if uploaded.size and uploaded.size > self.MAX_UPLOAD_SIZE:
                raise ValidationError('حجم هر فایل باید حداکثر 1 مگابایت باشد.')

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


class InvoiceUploadForm(forms.ModelForm):
    MAX_UPLOAD_SIZE = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.pdf',
    }

    customer = forms.ModelChoiceField(
        queryset=UserProfile.objects.none(),
        label='مشتری',
        empty_label='انتخاب مشتری',
    )
    confirm_assignment = forms.BooleanField(
        required=True,
        label='انتساب فاکتور به مشتری انتخاب شده را تایید می کنم.',
    )
    invoice_date = jDateField(
        label='تاریخ فاکتور',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs={'class': 'jalali-date', 'placeholder': '1403/01/31'}),
    )
    amount = forms.CharField(
        label='مبلغ (ریال)',
        widget=forms.TextInput(attrs={'class': 'amount-input', 'inputmode': 'numeric', 'dir': 'ltr'}),
    )

    class Meta:
        model = InvoiceRecord
        fields = ['customer', 'invoice_date', 'amount', 'reference_number', 'attachment', 'customer_visible_note', 'internal_note']
        widgets = {
            'reference_number': forms.TextInput(attrs={'dir': 'ltr'}),
            'attachment': forms.ClearableFileInput(attrs={
                'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
            }),
            'customer_visible_note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'متنی که مشتری بتواند ببیند'}),
            'internal_note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'فقط برای مالی و بازرگانی'}),
        }
        labels = {
            'invoice_date': 'تاریخ فاکتور',
            'amount': 'مبلغ (ریال)',
            'reference_number': 'شماره حواله',
            'attachment': 'تصویر یا فایل PDF',
            'customer_visible_note': 'توضیحات کارشناس بازرگانی برای مشتری',
            'internal_note': 'توضیحات داخلی',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = UserProfile.objects.filter(role='customer').select_related('user').order_by(
            'user__first_name', 'user__last_name', 'user__username'
        )
        self.fields['customer'].label_from_instance = self._customer_label
        for name, field in self.fields.items():
            if field.required:
                field.label = mark_safe(f'{field.label} <span style="color:#d00;">*</span>')

    @staticmethod
    def _customer_label(profile):
        full_name = profile.user.get_full_name().strip() or profile.user.username
        parts = [full_name]
        if profile.organization:
            parts.append(profile.organization)
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
        if not raw_amount.isdigit():
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت باشد.')
        amount = int(raw_amount)
        if amount <= 0:
            raise ValidationError('مبلغ باید یک عدد صحیح مثبت باشد.')
        return amount

    def clean_attachment(self):
        uploaded = self.cleaned_data.get('attachment')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError('فقط فایل های تصویری استاندارد و PDF مجاز است.')
        if uploaded.size and uploaded.size > self.MAX_UPLOAD_SIZE:
            raise ValidationError('حجم فایل باید حداکثر 5 مگابایت باشد.')
        return uploaded


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
    )

    username = forms.CharField(label='نام کاربر', max_length=150)
    first_name = forms.CharField(label='نام', max_length=50, required=False)
    last_name = forms.CharField(label='نام خانوادگی', max_length=50, required=False)
    phone = forms.CharField(label='شماره تماس', max_length=20, required=False)
    mobile = forms.CharField(label='شماره همراه', max_length=20, required=False)
    province = forms.CharField(label='استان', max_length=50, required=False)
    city = forms.CharField(label='شهر', max_length=50, required=False)
    address = forms.CharField(label='آدرس', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    organization = forms.CharField(label='نام مجموعه', max_length=100, required=False)
    password = forms.CharField(label='کلمه عبور', required=False, widget=forms.TextInput(attrs={'dir': 'ltr', 'inputmode': 'numeric'}))
    role = forms.ChoiceField(label='نقش', choices=ROLE_CHOICES)
    active_from = jDateField(
        label='تاریخ آغاز فعالیت',
        required=False,
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs={'class': 'jalali-date', 'placeholder': '1403/01/31'}),
    )
    valid_until = jDateField(
        label='تاریخ اعتبار',
        required=False,
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs={'class': 'jalali-date', 'placeholder': '1403/12/29'}),
    )
    force_password_change = forms.BooleanField(label='الزام تغییر رمز در ورود بعدی', required=False)
    suspended = forms.BooleanField(label='معلق', required=False, initial=False)
    is_active = forms.BooleanField(label='فعال', required=False, initial=True)

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.password_suggestion = kwargs.pop('password_suggestion', '')
        super().__init__(*args, **kwargs)

        if self.instance and not self.is_bound:
            profile = getattr(self.instance, 'profile', None)
            self.initial.update({
                'username': self.instance.username,
                'first_name': self.instance.first_name,
                'last_name': self.instance.last_name,
                'is_active': self.instance.is_active,
                'phone': getattr(profile, 'phone', ''),
                'mobile': getattr(profile, 'mobile', ''),
                'province': getattr(profile, 'province', ''),
                'city': getattr(profile, 'city', ''),
                'address': getattr(profile, 'address', ''),
                'organization': getattr(profile, 'organization', ''),
                'role': getattr(profile, 'role', 'customer'),
                'active_from': getattr(profile, 'active_from', None),
                'valid_until': getattr(profile, 'valid_until', None),
                'force_password_change': getattr(profile, 'force_password_change', False),
                'suspended': getattr(profile, 'suspended', False),
            })

        for name, field in self.fields.items():
            if name in {'password'}:
                continue
            if field.required:
                field.label = mark_safe(f'{field.label} <span style="color:#d00;">*</span>')

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if not username:
            raise ValidationError('نام کاربر الزامی است.')
        qs = User.objects.filter(username=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('این نام کاربری قبلا ثبت شده است.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        mobile = (cleaned_data.get('mobile') or '').strip()
        phone = (cleaned_data.get('phone') or '').strip()

        # For customers, check for duplicate mobile/phone
        if role == 'customer' and (mobile or phone):
            # Check for existing customer with same mobile
            if mobile:
                existing_by_mobile = UserProfile.objects.filter(mobile=mobile, role='customer')
                if self.instance:
                    existing_by_mobile = existing_by_mobile.exclude(user=self.instance)
                if existing_by_mobile.exists():
                    raise ValidationError('مشتری دیگری با این شماره همراه ثبت شده است.')

            # Check for existing customer with same phone
            if phone:
                existing_by_phone = UserProfile.objects.filter(phone=phone, role='customer')
                if self.instance:
                    existing_by_phone = existing_by_phone.exclude(user=self.instance)
                if existing_by_phone.exists():
                    raise ValidationError('مشتری دیگری با این شماره تماس ثبت شده است.')

        return cleaned_data

    def clean_password(self):
        password = (self.cleaned_data.get('password') or '').strip()
        if not password and not self.instance:
            raise ValidationError('کلمه عبور برای کاربر جدید الزامی است.')
        if password and (not password.isdigit() or len(password) != 5):
            raise ValidationError('کلمه عبور باید یک عدد 5 رقمی باشد.')
        return password

    def save(self):
        instance = self.instance or User()
        instance.username = self.cleaned_data['username']
        instance.first_name = self.cleaned_data.get('first_name', '').strip()
        instance.last_name = self.cleaned_data.get('last_name', '').strip()
        instance.is_active = self.cleaned_data.get('is_active', False)
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
        profile.save()
        return instance
