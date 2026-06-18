import hashlib
from io import BytesIO
import os
import random
import re
import time as _time
from zoneinfo import ZoneInfo

import jdatetime
from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.forms import inlineformset_factory
from django.utils import timezone
from django.utils.safestring import mark_safe
from django_jalali.forms import jDateField, jDateInput
from PIL import Image, ImageOps

DISPLAY_TZ = ZoneInfo(getattr(settings, 'APP_DISPLAY_TIME_ZONE', 'Asia/Tehran'))

from .models import Counterparty, CounterpartyBankAccount, CustomerOrder, CustomerOrderItem, CustomerSalesAssignment, DailyPaymentAssignment, DailyPaymentPlan, InvoiceRecord, PaymentRecord, PriceList, ProformaInvoice, ReconciliationMessage, ReconciliationThread, SystemSettings, UploadSettings, UserProfile

STAFF_ROLES = {'staff', 'finance', 'finance_manager', 'commercial', 'commercial_manager', 'sales', 'sales_manager', 'data_entry'}
MANAGER_ROLES = {'finance_manager', 'commercial_manager', 'sales_manager'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff'}
DEFAULT_RECEIPT_MAX_UPLOAD_SIZE = 1 * 1024 * 1024
DEFAULT_INVOICE_MAX_UPLOAD_SIZE = 5 * 1024 * 1024
RECONCILIATION_ATTACHMENT_MAX_UPLOAD_SIZE = 10 * 1024 * 1024
# فرمت‌های اجرایی، اسکریپتی و نصب‌کننده که ریسک امنیتی دارند و در پیوست گفتگو مجاز نیستند
RECONCILIATION_BLOCKED_ATTACHMENT_EXTENSIONS = {
    '.exe', '.com', '.bat', '.cmd', '.msi', '.msix', '.msixbundle', '.msp', '.mst',
    '.scr', '.pif', '.cpl', '.dll', '.sys', '.drv', '.vxd', '.gadget', '.application',
    '.js', '.jse', '.vb', '.vbs', '.vbe', '.ws', '.wsc', '.wsf', '.wsh',
    '.ps1', '.ps1xml', '.ps2', '.psc1', '.psc2', '.msh', '.msh1', '.msh2',
    '.lnk', '.inf', '.reg', '.scf', '.hta', '.jar', '.jnlp',
    '.php', '.php3', '.php4', '.php5', '.phtml', '.asp', '.aspx', '.jsp', '.jspx',
    '.cgi', '.pl', '.py', '.rb', '.sh',
    '.apk', '.app', '.command', '.dmg', '.run', '.bin', '.action', '.workflow', '.out',
}
IMAGE_RESIZE_MAX_SIDE = 2200
PROFILE_AVATAR_MAX_UPLOAD_SIZE = 512 * 1024
PROFILE_AVATAR_MAX_SIDE = 512
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


def _role_for_user(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    if user.is_superuser:
        return 'admin'
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return 'staff' if user.is_staff else ''


def _customer_profiles_for_user(user=None):
    profiles = _active_customer_profiles()
    if _role_for_user(user) == 'sales':
        assigned_ids = CustomerSalesAssignment.objects.filter(sales_user=user).values_list('customer_id', flat=True)
        return profiles.filter(user_id__in=assigned_ids)
    return profiles


def _active_sales_users():
    return User.objects.filter(
        is_active=True,
        profile__role__in=['sales', 'sales_manager'],
        profile__suspended=False,
    ).select_related('profile').order_by('first_name', 'last_name', 'username')


def _receipt_max_upload_size():
    settings = _upload_settings()
    return settings.receipt_max_upload_size_bytes if settings else DEFAULT_RECEIPT_MAX_UPLOAD_SIZE


# کش تنظیمات اجباری بودن فیلدها — هر ۶۰ ثانیه از دیتابیس می‌خواند
_frc_cache: dict = {}
_frc_cache_ts: dict = {}
_FRC_TTL = 60


def _apply_field_config(form_instance, form_name: str) -> None:
    """
    اگر ادمین override تنظیم کرده (is_required != None) آن را اعمال می‌کند.
    اگر is_required=None باشد، پیشفرض کد دست‌نخورده می‌ماند.
    """
    for field_name, override in _get_field_required_config(form_name).items():
        if override is not None and field_name in form_instance.fields and not form_instance.fields[field_name].disabled:
            form_instance.fields[field_name].required = override


def _get_field_required_config(form_name: str) -> dict:
    """
    Returns {field_name: is_required_or_None} for the given form, cached for 60s.
    None means 'use code default' (no override from admin).
    """
    now = _time.monotonic()
    if form_name not in _frc_cache or now - _frc_cache_ts.get(form_name, 0) > _FRC_TTL:
        try:
            from .models import FieldRequirementConfig
            _frc_cache[form_name] = {
                c.field_name: c.is_required  # None = use code default
                for c in FieldRequirementConfig.objects.filter(form_name=form_name)
            }
        except Exception:
            _frc_cache[form_name] = {}
        _frc_cache_ts[form_name] = now
    return _frc_cache[form_name]


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


def _crop_uploaded_image(uploaded, crop_rect):
    if not crop_rect:
        return uploaded

    try:
        uploaded.seek(0)
        image = Image.open(uploaded)
        image = ImageOps.exif_transpose(image)
        left, top, right, bottom = crop_rect
        left = max(0, int(round(left)))
        top = max(0, int(round(top)))
        right = min(image.width, int(round(right)))
        bottom = min(image.height, int(round(bottom)))
        if right > left and bottom > top:
            image = image.crop((left, top, right, bottom))
        image.thumbnail((PROFILE_AVATAR_MAX_SIDE, PROFILE_AVATAR_MAX_SIDE), Image.Resampling.LANCZOS)
        image = _flatten_for_jpeg(image)

        output = BytesIO()
        image.save(output, format='JPEG', quality=92, optimize=True, progressive=True)
        output.seek(0)
        return SimpleUploadedFile(
            _optimized_image_name(uploaded.name),
            output.getvalue(),
            content_type='image/jpeg',
        )
    except Exception:
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
        fields = [
            'avatar_image', 'avatar_preset', 'phone', 'second_mobile',
            'representative_name', 'representative_mobile', 'delegate_sms_to_representative',
            'organization', 'address', 'second_address',
        ]
        widgets = {
            'avatar_image': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif'}),
            'phone': forms.TextInput(attrs={'inputmode': 'tel'}),
            'second_mobile': forms.TextInput(attrs={'inputmode': 'tel'}),
            'representative_mobile': forms.TextInput(attrs={'inputmode': 'tel'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'second_address': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'avatar_image': 'عکس نمایه',
            'avatar_preset': 'نمایه پیش‌فرض',
            'phone': 'شماره تلفن',
            'second_mobile': 'شماره همراه دوم',
            'representative_name': 'نام نماینده',
            'representative_mobile': 'موبایل نماینده',
            'delegate_sms_to_representative': 'ارسال پیامک‌ها به موبایل نماینده',
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
        _apply_field_config(self, 'profile')

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip()

    def clean_avatar_image(self):
        uploaded = self.cleaned_data.get('avatar_image')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise ValidationError('فقط فایل تصویری برای عکس نمایه مجاز است.')

        def float_value(name):
            value = self.data.get(name)
            if value is None or value == '':
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        crop_x = float_value('avatar_crop_x')
        crop_y = float_value('avatar_crop_y')
        crop_width = float_value('avatar_crop_width')
        crop_height = float_value('avatar_crop_height')
        crop_rect = None
        if crop_x is not None or crop_y is not None or crop_width is not None or crop_height is not None:
            if crop_x is None or crop_y is None or crop_width is None or crop_height is None:
                raise ValidationError('مقادیر برش عکس نمایه نامعتبر است.')
            if crop_width <= 0 or crop_height <= 0:
                raise ValidationError('مقادیر برش عکس نمایه نامعتبر است.')
            crop_rect = (crop_x, crop_y, crop_x + crop_width, crop_y + crop_height)

        cropped = _crop_uploaded_image(uploaded, crop_rect)
        return _optimize_uploaded_image(cropped, PROFILE_AVATAR_MAX_UPLOAD_SIZE, max_side=PROFILE_AVATAR_MAX_SIDE)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('delegate_sms_to_representative') and not (cleaned_data.get('representative_mobile') or '').strip():
            self.add_error('representative_mobile', 'برای تفویض پیامک، ثبت موبایل نماینده لازم است.')
        return cleaned_data

    def save_avatar_fields(self):
        changed = False
        if 'avatar_preset' in self.changed_data:
            self.instance.avatar_preset = self.cleaned_data.get('avatar_preset') or 'neutral_1'
            changed = True
        if 'avatar_image' in self.changed_data:
            avatar_image = self.cleaned_data.get('avatar_image')
            self.instance.avatar_image = '' if avatar_image is False else avatar_image
            changed = True
        if changed:
            self.instance.save(update_fields=['avatar_preset', 'avatar_image'])
        return changed

    def changed_profile_fields(self):
        labels = {
            'email': 'ایمیل',
            'phone': 'شماره تلفن',
            'second_mobile': 'شماره همراه دوم',
            'representative_name': 'نام نماینده',
            'representative_mobile': 'موبایل نماینده',
            'delegate_sms_to_representative': 'ارسال پیامک‌ها به موبایل نماینده',
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
            old_display = old_value or '-'
            new_display = new_value or '-'
            if field_name == 'delegate_sms_to_representative':
                old_value = bool(getattr(self.instance, field_name, False))
                new_value = bool(self.cleaned_data.get(field_name))
                old_display = 'بله' if old_value else 'خیر'
                new_display = 'بله' if new_value else 'خیر'
            changes.append({
                'name': field_name,
                'field': labels[field_name],
                'old': old_display,
                'new': new_display,
                'raw_old': old_value,
                'raw_new': new_value,
            })
        return changes

    def changes_payload(self):
        return {
            item['name']: {
                'old': item.get('raw_old', '' if item['old'] == '-' else item['old']),
                'new': item.get('raw_new', '' if item['new'] == '-' else item['new']),
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
            'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
        }),
        label='فایل فیش',
        help_text='یک فایل تصویر یا PDF انتخاب کنید. حداکثر حجم: ۱ مگابایت.',
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

        # اعمال تنظیمات اجباری بودن فیلدها از دیتابیس
        field_config = _get_field_required_config('payment')
        for field_name, is_req in field_config.items():
            if field_name in self.fields and not self.fields[field_name].disabled:
                self.fields[field_name].required = is_req

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
        today = jdatetime.date.fromgregorian(date=timezone.localdate(timezone=DISPLAY_TZ))
        if pay_date is None:
            return today
        if pay_date > today:
            raise ValidationError(
                f'تاریخ واریز ({pay_date.strftime("%Y/%m/%d")}) در آینده است. '
                'تاریخ روی فیش را دوباره بررسی و وارد کنید.'
            )
        return pay_date

    def clean_receipt_images(self):
        files = self.files.getlist('receipt_images')
        has_existing_files = bool(self.instance.pk and self.instance.receipts.exists())
        if not files and not has_existing_files:
            raise ValidationError('حداقل یک فایل فیش لازم است.')
        if len(files) > 1:
            raise ValidationError('فقط یک فایل در هر بار ثبت مجاز است.')

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
        _apply_field_config(self, 'payment_staff')

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
    rejection_reason = forms.ChoiceField(
        choices=[('', '---------')] + list(PaymentRecord.REJECTION_REASON_CHOICES),
        required=False,
        label='دلیل رد',
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

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        rejection_reason = cleaned_data.get('rejection_reason')
        note = (cleaned_data.get('note') or '').strip()

        if status == PaymentRecord.STATUS_REJECTED:
            if not rejection_reason:
                self.add_error('rejection_reason', 'انتخاب دلیل رد الزامی است.')
            elif rejection_reason == PaymentRecord.REJECTION_REASON_OTHER and not note:
                self.add_error('note', 'برای دلیل «سایر»، نوشتن توضیح الزامی است.')

        return cleaned_data


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


class CounterpartyManagementForm(forms.ModelForm):
    """فرم کامل ایجاد/ویرایش طرف حساب از پنل مدیریت کاربران."""

    password = forms.CharField(
        label='کلمه عبور',
        required=False,
        widget=forms.TextInput(attrs={'dir': 'ltr', 'inputmode': 'latin'}),
        help_text='فقط در صورت ایجاد حساب کاربری جدید پر کنید.',
    )
    username = forms.CharField(
        label='نام کاربری (شماره موبایل)',
        required=False,
        widget=forms.TextInput(attrs={'dir': 'ltr'}),
        help_text='اگر پر شود، یک حساب کاربری برای ورود ایجاد می‌شود.',
    )

    class Meta:
        model = Counterparty
        fields = ['name', 'first_name', 'last_name', 'phone', 'description', 'status']
        labels = {
            'name': 'نام سازمان / شرکت',
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'phone': 'شماره تماس',
            'description': 'توضیحات',
            'status': 'وضعیت',
        }
        widgets = {
            'phone': forms.TextInput(attrs={'inputmode': 'tel', 'dir': 'ltr'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_config(self, 'counterparty')
        # نمایش نام کاربری فعلی اگر حساب دارد
        if self.instance and self.instance.pk and self.instance.user_id:
            self.initial['username'] = self.instance.user.username
            self.fields['password'].help_text = 'در صورت خالی بودن، رمز تغییر نمی‌کند.'

    def save(self, commit=True):
        cp = super().save(commit=False)
        username = (self.cleaned_data.get('username') or '').strip()
        password = (self.cleaned_data.get('password') or '').strip()

        if username:
            if cp.user_id:
                # به‌روزرسانی حساب موجود
                u = cp.user
                u.username = username
                if password:
                    u.set_password(password)
                u.first_name = cp.first_name
                u.last_name = cp.last_name
                u.save()
            else:
                # ایجاد حساب جدید
                u = User(username=username, first_name=cp.first_name, last_name=cp.last_name, is_active=True)
                if password:
                    u.set_password(password)
                else:
                    u.set_unusable_password()
                u.save()
                cp.user = u

            # نقش کاربری را به «طرف حساب» ست کن
            try:
                from .models import UserProfile
                profile = u.profile
                if profile.role != 'counterparty':
                    profile.role = 'counterparty'
                    profile.save(update_fields=['role'])
            except Exception:
                pass

        if commit:
            cp.save()
        return cp


class CounterpartyBankAccountForm(forms.ModelForm):
    class Meta:
        model = CounterpartyBankAccount
        fields = ['bank_name', 'city', 'branch', 'account_number', 'account_owner', 'iban', 'is_primary']
        labels = {
            'bank_name': 'نام بانک',
            'city': 'شهر',
            'branch': 'شعبه',
            'account_number': 'شماره حساب',
            'account_owner': 'نام صاحب حساب',
            'iban': 'شماره شبا',
            'is_primary': 'حساب اصلی',
        }
        widgets = {
            'bank_name': forms.TextInput(attrs={'class': 'bank-autocomplete-input', 'data-bank-type': 'beneficiary', 'autocomplete': 'off'}),
            'account_number': forms.TextInput(attrs={'dir': 'ltr'}),
            'iban': forms.TextInput(attrs={'dir': 'ltr', 'placeholder': 'IR000000000000000000000000'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_config(self, 'counterparty_bank')
        for field in self.fields.values():
            if field.label != 'حساب اصلی':
                field.required = False


CounterpartyBankAccountFormSet = inlineformset_factory(
    Counterparty,
    CounterpartyBankAccount,
    form=CounterpartyBankAccountForm,
    extra=1,
    can_delete=True,
)


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
        self.user = kwargs.pop('user', None)
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

        self.fields['customer'].queryset = _customer_profiles_for_user(self.user)
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
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = _customer_profiles_for_user(self.user)
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
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = _customer_profiles_for_user(self.user)
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


class CustomerOrderForm(forms.ModelForm):
    class Meta:
        model = CustomerOrder
        fields = ['title', 'customer_note']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'مثلا سفارش قطعات اردیبهشت'}),
            'customer_note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'توضیحات تکمیلی، زمان تحویل یا شرایط مورد نظر'}),
        }
        labels = {
            'title': 'عنوان سفارش',
            'customer_note': 'توضیحات سفارش',
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)
        _apply_field_config(self, 'order')

    @staticmethod
    def _sales_label(user):
        return user.get_full_name().strip() or user.username


class CustomerOrderItemForm(forms.ModelForm):
    class Meta:
        model = CustomerOrderItem
        fields = ['product_name', 'quantity', 'unit', 'note']
        widgets = {
            'product_name': forms.TextInput(attrs={
                'placeholder': 'نام کالا',
                'class': 'product-name-input',
                'autocomplete': 'off',
            }),
            'quantity': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'inputmode': 'decimal'}),
            'unit': forms.TextInput(attrs={'placeholder': 'واحد (مثلاً: عدد، کارتن)'}),
            'note': forms.TextInput(attrs={'placeholder': 'کد کالا، مدل، رنگ یا توضیح'}),
        }
        labels = {
            'product_name': 'نام کالا',
            'quantity': 'تعداد',
            'unit': 'واحد',
            'note': 'توضیح / کد کالا',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].required = False
        self.fields['quantity'].required = False
        _apply_field_config(self, 'order_item')


CustomerOrderItemFormSet = inlineformset_factory(
    CustomerOrder,
    CustomerOrderItem,
    form=CustomerOrderItemForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class StaffOrderUpdateForm(forms.ModelForm):
    sales_expert = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='کارشناس فروش',
        required=False,
        empty_label='بدون تخصیص',
    )

    class Meta:
        model = CustomerOrder
        fields = ['status', 'sales_expert', 'staff_note']
        widgets = {
            'staff_note': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'status': 'وضعیت سفارش',
            'staff_note': 'توضیح داخلی فروش',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sales_expert'].queryset = _active_sales_users()
        self.fields['sales_expert'].label_from_instance = CustomerOrderForm._sales_label


class SalesAssignmentBulkForm(forms.Form):
    customers = forms.ModelMultipleChoiceField(
        queryset=UserProfile.objects.none(),
        label='مشتریان',
        widget=forms.SelectMultiple(attrs={'size': 10, 'data-customer-select': '1'}),
    )
    sales_user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='کارشناس فروش',
        empty_label='انتخاب کارشناس',
    )
    transfer_open_orders = forms.BooleanField(
        label='سفارش های باز این مشتریان نیز به کارشناس جدید منتقل شود',
        required=False,
        initial=True,
    )
    note = forms.CharField(
        label='توضیح',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = _active_customer_profiles()
        self.fields['customers'].label_from_instance = InvoiceUploadForm._customer_label
        self.fields['sales_user'].queryset = _active_sales_users()
        self.fields['sales_user'].label_from_instance = CustomerOrderForm._sales_label

    def clean_customers(self):
        profiles = self.cleaned_data['customers']
        if not profiles:
            raise ValidationError('حداقل یک مشتری را انتخاب کنید.')
        return [profile.user for profile in profiles]


class OrderProformaUploadForm(forms.Form):
    title = forms.CharField(label='عنوان پیش فاکتور', max_length=120, required=False)
    valid_until = jDateField(
        label='اعتبار تا',
        input_formats=['%Y/%m/%d'],
        widget=jDateInput(format='%Y/%m/%d', attrs=_date_input_attrs(placeholder='1403/01/31')),
        required=True,
    )
    files = MultipleFileField(
        label='فایل های پیش فاکتور',
        required=True,
        widget=MultipleFileInput(attrs={
            'accept': '.jpg,.jpeg,.png,.gif,.webp,.bmp,.tif,.tiff,.pdf,image/*,application/pdf',
            'multiple': True,
        }),
    )
    note = forms.CharField(
        label='توضیح داخلی',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_config(self, 'order_proforma')

    def clean_files(self):
        files = self.cleaned_data.get('files') or []
        if not files:
            raise ValidationError('حداقل یک فایل پیش فاکتور را انتخاب کنید.')
        for uploaded in files:
            ext = os.path.splitext(uploaded.name or '')[1].lower()
            if ext not in ProformaInvoiceForm.ALLOWED_EXTENSIONS:
                raise ValidationError('فقط فایل های تصویری استاندارد و PDF مجاز است.')
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
    # طرف حساب از این فرم ایجاد نمی‌شود — فقط از بخش «مدیریت طرف حساب‌ها»
    ROLE_CHOICES = (
        ('customer',          '👤 مشتری'),
        ('commercial',        '🏬 واحد بازرگانی'),
        ('commercial_manager','🏬 مدیر بازرگانی'),
        ('finance',           '💰 واحد مالی'),
        ('finance_manager',   '💰 مدیر مالی'),
        ('sales',             '📊 فروش'),
        ('sales_manager',     '📊 مدیر فروش'),
        ('data_entry',        '✏️ تکمیل اطلاعات فیش'),
        ('staff',             '🔧 کارمند'),
    )

    first_name = forms.CharField(label='نام', max_length=50, required=True)
    last_name = forms.CharField(label='نام خانوادگی', max_length=50, required=True)
    phone = forms.CharField(label='شماره تماس', max_length=20, required=False)
    mobile = forms.CharField(label='شماره همراه', max_length=20, required=True)
    representative_name = forms.CharField(label='نام نماینده', max_length=100, required=False)
    representative_mobile = forms.CharField(label='موبایل نماینده', max_length=20, required=False)
    delegate_sms_to_representative = forms.BooleanField(label='ارسال پیامک‌ها به موبایل نماینده', required=False)
    province = forms.CharField(label='استان', max_length=50, required=True)
    city = forms.CharField(label='شهر', max_length=50, required=True)
    address = forms.CharField(label='آدرس', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    organization = forms.CharField(label='نام مجموعه', max_length=100, required=True)
    email = forms.EmailField(label='ایمیل', required=False)
    avatar_image = forms.ImageField(
        label='عکس نمایه',
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif'}),
    )
    avatar_preset = forms.ChoiceField(label='نمایه پیش‌فرض', choices=UserProfile.AVATAR_PRESET_CHOICES, required=False)
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
    can_access_reconciliation = forms.BooleanField(label='دسترسی مغایرت‌گیری', required=False)
    is_active = forms.BooleanField(label='فعال', required=False, initial=True)
    accounting_code = forms.CharField(label='کد تفضیلی (حسابداری)', max_length=50, required=False)

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.password_suggestion = kwargs.pop('password_suggestion', '')
        super().__init__(*args, **kwargs)

        if self.instance:
            self.fields.pop('password', None)
            # در حالت ویرایش، تاریخ‌ها اجباری نیستند — اگر خالی بمانند مقدار قبلی حفظ می‌شود
            self.fields['active_from'].required = False
            self.fields['valid_until'].required = False

        if self.instance and not self.is_bound:
            profile = getattr(self.instance, 'profile', None)
            self.initial.update({
                'first_name': self.instance.first_name,
                'last_name': self.instance.last_name,
                'phone': getattr(profile, 'phone', ''),
                'mobile': getattr(profile, 'mobile', ''),
                'representative_name': getattr(profile, 'representative_name', ''),
                'representative_mobile': getattr(profile, 'representative_mobile', ''),
                'delegate_sms_to_representative': getattr(profile, 'delegate_sms_to_representative', False),
                'province': getattr(profile, 'province', ''),
                'city': getattr(profile, 'city', ''),
                'address': getattr(profile, 'address', ''),
                'organization': getattr(profile, 'organization', ''),
                'email': self.instance.email,
                'avatar_preset': getattr(profile, 'avatar_preset', 'neutral_1'),
                'role': getattr(profile, 'role', 'customer'),
                'active_from': getattr(profile, 'active_from', None),
                'valid_until': getattr(profile, 'valid_until', None),
                'force_password_change': getattr(profile, 'force_password_change', False),
                'suspended': getattr(profile, 'suspended', False),
                'can_view_invoices': getattr(profile, 'can_view_invoices', False),
                'can_upload_invoices': getattr(profile, 'can_upload_invoices', False),
                'can_edit_payment_details': getattr(profile, 'can_edit_payment_details', False),
                'can_access_reconciliation': getattr(profile, 'can_access_reconciliation', False),
                'accounting_code': getattr(profile, 'accounting_code', ''),
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
        representative_mobile = (cleaned_data.get('representative_mobile') or '').strip()

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

        if not active_from and not self.instance:
            self.add_error('active_from', 'تاریخ آغاز فعالیت الزامی است.')

        if not valid_until and not self.instance:
            self.add_error('valid_until', 'تاریخ اعتبار الزامی است.')

        if not password and not self.instance:
            self.add_error('password', 'کلمه عبور الزامی است.')

        if cleaned_data.get('delegate_sms_to_representative') and not representative_mobile:
            self.add_error('representative_mobile', 'برای تفویض پیامک، ثبت موبایل نماینده لازم است.')

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

    def clean_avatar_image(self):
        uploaded = self.cleaned_data.get('avatar_image')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise ValidationError('فقط فایل تصویری برای عکس نمایه مجاز است.')
        return _optimize_uploaded_image(uploaded, PROFILE_AVATAR_MAX_UPLOAD_SIZE, max_side=PROFILE_AVATAR_MAX_SIDE)

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
        profile.representative_name = (self.cleaned_data.get('representative_name') or '').strip()
        profile.representative_mobile = (self.cleaned_data.get('representative_mobile') or '').strip()
        profile.delegate_sms_to_representative = self.cleaned_data.get('delegate_sms_to_representative', False)
        profile.province = (self.cleaned_data.get('province') or '').strip()
        profile.city = (self.cleaned_data.get('city') or '').strip()
        profile.address = (self.cleaned_data.get('address') or '').strip()
        profile.organization = (self.cleaned_data.get('organization') or '').strip()
        profile.role = self.cleaned_data['role']
        if self.cleaned_data.get('active_from') is not None:
            profile.active_from = self.cleaned_data['active_from']
        if self.cleaned_data.get('valid_until') is not None:
            profile.valid_until = self.cleaned_data['valid_until']
        profile.force_password_change = self.cleaned_data.get('force_password_change', False)
        profile.suspended = self.cleaned_data.get('suspended', False)
        profile.can_view_invoices = self.cleaned_data.get('can_view_invoices', False)
        profile.can_upload_invoices = self.cleaned_data.get('can_upload_invoices', False)
        profile.can_edit_payment_details = self.cleaned_data.get('can_edit_payment_details', False)
        profile.can_access_reconciliation = self.cleaned_data.get('can_access_reconciliation', False)
        profile.accounting_code = (self.cleaned_data.get('accounting_code') or '').strip()
        profile.avatar_preset = self.cleaned_data.get('avatar_preset') or 'neutral_1'
        if self.cleaned_data.get('avatar_image'):
            profile.avatar_image = self.cleaned_data['avatar_image']
        profile.save()
        return instance


class UserAccessManagementForm(forms.Form):
    """فرم سبک مخصوص «مدیریت دسترسی‌ها» — فقط نقش (در صورت اجازه) و فلگ‌های دسترسی/وضعیت."""

    ROLE_CHOICES = (
        ('commercial',        '🏬 واحد بازرگانی'),
        ('commercial_manager','🏬 مدیر بازرگانی'),
        ('finance',           '💰 واحد مالی'),
        ('finance_manager',   '💰 مدیر مالی'),
        ('sales',             '📊 فروش'),
        ('sales_manager',     '📊 مدیر فروش'),
        ('data_entry',        '✏️ تکمیل اطلاعات فیش'),
        ('staff',             '🔧 کارمند'),
        ('warranty',          '🛡️ کارشناس گارانتی'),
        ('warranty_manager',  '🛡️ مدیر گارانتی'),
    )

    role = forms.ChoiceField(label='نقش', choices=ROLE_CHOICES, required=True)
    can_view_invoices = forms.BooleanField(label='دسترسی مشاهده فاکتورها', required=False)
    can_upload_invoices = forms.BooleanField(label='دسترسی بارگذاری فاکتورها', required=False)
    can_edit_payment_details = forms.BooleanField(label='دسترسی تکمیل اطلاعات فیش‌ها', required=False)
    can_access_reconciliation = forms.BooleanField(label='دسترسی مغایرت‌گیری', required=False)
    is_active = forms.BooleanField(label='فعال', required=False)
    suspended = forms.BooleanField(label='معلق', required=False)

    def __init__(self, *args, **kwargs):
        self.target = kwargs.pop('target')
        self.allow_role_change = kwargs.pop('allow_role_change', False)
        super().__init__(*args, **kwargs)

        if not self.allow_role_change:
            self.fields.pop('role')

        if not self.is_bound:
            profile = self.target.profile
            self.initial.update({
                'role': profile.role,
                'can_view_invoices': profile.can_view_invoices,
                'can_upload_invoices': profile.can_upload_invoices,
                'can_edit_payment_details': profile.can_edit_payment_details,
                'can_access_reconciliation': profile.can_access_reconciliation,
                'is_active': self.target.is_active,
                'suspended': profile.suspended,
            })

    def save(self):
        profile = self.target.profile
        if 'role' in self.cleaned_data:
            profile.role = self.cleaned_data['role']
            self.target.is_staff = self.target.is_superuser or profile.role in STAFF_ROLES or profile.role in {'warranty', 'warranty_manager'}
        profile.can_view_invoices = self.cleaned_data.get('can_view_invoices', False)
        profile.can_upload_invoices = self.cleaned_data.get('can_upload_invoices', False)
        profile.can_edit_payment_details = self.cleaned_data.get('can_edit_payment_details', False)
        profile.can_access_reconciliation = self.cleaned_data.get('can_access_reconciliation', False)
        profile.suspended = self.cleaned_data.get('suspended', False)
        self.target.is_active = self.cleaned_data.get('is_active', True)
        self.target.save()
        profile.save()
        return self.target


def _reconciliation_staff_queryset(customer_visible_only=False):
    qs = (
        User.objects
        .filter(is_active=True, profile__suspended=False)
        .exclude(profile__role='customer')
        .select_related('profile')
        .order_by('first_name', 'last_name', 'username')
    )
    if customer_visible_only:
        qs = qs.filter(profile__can_access_reconciliation=True)
    return qs


def _reconciliation_customer_queryset():
    return (
        User.objects
        .filter(is_active=True, profile__role='customer', profile__suspended=False)
        .select_related('profile')
        .order_by('first_name', 'last_name', 'username')
    )


class ReconciliationThreadForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        label='مشتری',
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={'size': 6}),
    )
    staff_participants = forms.ModelMultipleChoiceField(
        label='کارشناسان گفتگو',
        queryset=User.objects.none(),
        required=True,
        widget=forms.SelectMultiple(attrs={'size': 6}),
    )

    @staticmethod
    def _label_from_instance(user):
        profile = getattr(user, 'profile', None)
        return profile.display_name if profile else user.username

    class Meta:
        model = ReconciliationThread
        fields = ['title', 'customer', 'staff_participants', 'is_internal', 'document_type', 'document_id']
        labels = {
            'title': 'عنوان مغایرت',
            'document_type': 'نوع سند مرجع',
            'document_id': 'شناسه سند',
            'is_internal': '🔒 گفتگوی داخلی (فقط کارکنان)',
        }
        widgets = {
            'document_id': forms.NumberInput(attrs={'min': 1, 'placeholder': 'مثلا 125'}),
            'is_internal': forms.CheckboxInput(attrs={'class': 'internal-checkbox'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        is_customer = bool(user and _role_for_user(user) == 'customer')
        self.fields['staff_participants'].queryset = _reconciliation_staff_queryset(customer_visible_only=is_customer)
        self.fields['staff_participants'].label_from_instance = self._label_from_instance
        self.fields['customer'].queryset = _reconciliation_customer_queryset()
        self.fields['customer'].label_from_instance = self._label_from_instance
        if is_customer:
            self.fields.pop('customer', None)
            self.fields.pop('is_internal', None)

    def clean_staff_participants(self):
        staff = self.cleaned_data.get('staff_participants')
        if not staff:
            raise ValidationError('حداقل یک کارشناس منتخب را انتخاب کنید.')
        return staff

    def clean(self):
        cleaned_data = super().clean()
        is_internal = cleaned_data.get('is_internal')
        if self.user and _role_for_user(self.user) != 'customer' and not is_internal and not cleaned_data.get('customer'):
            self.add_error('customer', 'انتخاب مشتری الزامی است.')
        document_type = cleaned_data.get('document_type')
        document_id = cleaned_data.get('document_id')
        if document_type and document_type != ReconciliationThread.DOC_OTHER and not document_id:
            self.add_error('document_id', 'برای لینک کردن سند، شناسه سند را وارد کنید.')
        return cleaned_data


class ReconciliationMessageForm(forms.ModelForm):
    class Meta:
        model = ReconciliationMessage
        fields = ['body', 'attachment', 'document_type', 'document_id']
        labels = {
            'body': 'پیام',
            'attachment': 'پیوست فایل',
            'document_type': 'ارجاع به سند',
            'document_id': 'شناسه سند',
        }
        widgets = {
            'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'پیام خود را بنویسید...'}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'chat-attachment-input'}),
            'document_id': forms.NumberInput(attrs={'min': 1, 'placeholder': 'شناسه سند'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['body'].required = False

    def clean_attachment(self):
        uploaded = self.cleaned_data.get('attachment')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        if ext in RECONCILIATION_BLOCKED_ATTACHMENT_EXTENSIONS:
            raise ValidationError('این نوع فایل به دلیل ریسک امنیتی قابل ارسال نیست.')
        if uploaded.size and uploaded.size > RECONCILIATION_ATTACHMENT_MAX_UPLOAD_SIZE:
            raise ValidationError(f'حجم فایل باید حداکثر {_size_label(RECONCILIATION_ATTACHMENT_MAX_UPLOAD_SIZE)} باشد.')
        return uploaded

    def clean(self):
        cleaned_data = super().clean()
        document_type = cleaned_data.get('document_type')
        document_id = cleaned_data.get('document_id')
        if document_type and not document_id:
            self.add_error('document_id', 'شناسه سند ارجاع‌شده را وارد کنید.')
        if not (cleaned_data.get('body') or '').strip() and not cleaned_data.get('attachment'):
            raise ValidationError('برای ارسال، نوشتن متن پیام یا پیوست‌کردن فایل الزامی است.')
        return cleaned_data


class SystemLogoSettingsForm(forms.ModelForm):
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    MAX_SIZE_BYTES = 512 * 1024
    MAX_WIDTH = 600
    MAX_HEIGHT = 220
    MIN_WIDTH = 120
    MIN_HEIGHT = 32

    clear_logo = forms.BooleanField(label='حذف لوگوی سفارشی و استفاده از لوگوی پیش‌فرض', required=False)

    class Meta:
        model = SystemSettings
        fields = ['system_logo', 'clear_logo']
        labels = {'system_logo': 'لوگوی شرکت'}
        widgets = {
            'system_logo': forms.ClearableFileInput(attrs={
                'accept': 'image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp',
            }),
        }
        help_texts = {
            'system_logo': 'فرمت مجاز: PNG، JPG یا WEBP. حجم حداکثر 512KB. ابعاد پیشنهادی حداکثر 600×220 پیکسل.',
        }

    def clean_system_logo(self):
        uploaded = self.cleaned_data.get('system_logo')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError('فرمت لوگو باید PNG، JPG یا WEBP باشد.')
        if uploaded.size and uploaded.size > self.MAX_SIZE_BYTES:
            raise ValidationError('حجم لوگو باید حداکثر 512KB باشد.')
        try:
            uploaded.seek(0)
            image = Image.open(uploaded)
            image.verify()
            width, height = image.size
            uploaded.seek(0)
        except Exception:
            raise ValidationError('فایل لوگو معتبر نیست یا قابل خواندن نمی‌باشد.')
        if width > self.MAX_WIDTH or height > self.MAX_HEIGHT:
            raise ValidationError('ابعاد لوگو باید حداکثر 600×220 پیکسل باشد.')
        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            raise ValidationError('ابعاد لوگو بسیار کوچک است. حداقل اندازه مجاز 120×32 پیکسل است.')
        return uploaded

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('clear_logo'):
            instance.system_logo = None
        if commit:
            instance.save()
        return instance


class SystemMenuSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ['customer_warranty_menu_enabled', 'accounting_code_import_enabled']
        labels = {
            'customer_warranty_menu_enabled': 'نمایش منوی «گارانتی و خدمات پس از فروش» برای مشتریان',
            'accounting_code_import_enabled': 'فعال بودن دکمه «ورود کد تفضیلی از اکسل» در صفحه مشتریان',
        }
