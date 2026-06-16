import uuid
import os
import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django_jalali.db import models as jmodels


def _safe_upload_extension(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    safe_ext = ''.join(ch for ch in ext if ch in '.abcdefghijklmnopqrstuvwxyz0123456789')
    if safe_ext == '.' or len(safe_ext) > 16:
        return ''
    return safe_ext


def _upload_actor_id(instance):
    for attr in ('user', 'customer', 'sender', 'uploaded_by', 'issued_by', 'requested_by'):
        value = getattr(instance, f'{attr}_id', None)
        if value:
            return value
    payment = getattr(instance, 'payment', None)
    if payment:
        return getattr(payment, 'user_id', None) or getattr(payment, 'id', None)
    return 'system'


def _unique_upload_path(instance, filename, folder, model_name):
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    actor_id = _upload_actor_id(instance)
    token = uuid.uuid4().hex[:12]
    ext = _safe_upload_extension(filename)
    return f'{folder}/{model_name}_user{actor_id}_{timestamp}_{token}{ext}'


def login_ad_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'login_ads', 'loginadvertisement')


def payment_record_receipt_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'receipts', 'paymentrecord')


def payment_receipt_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'receipts', 'paymentreceipt')


def invoice_attachment_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'invoices', 'invoicerecord')


def reconciliation_attachment_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'reconciliation_attachments', 'reconciliationmessage')


def invoice_extraction_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'invoice_extractions', 'invoiceextractionjob')


def price_list_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'price_lists', 'pricelist')


def proforma_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'proformas', 'proformainvoice')


def profile_avatar_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'profile_avatars', 'userprofile')


def system_logo_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'system_branding', 'systemlogo')


class Counterparty(models.Model):
    STATUS_ACTIVE    = 'active'
    STATUS_INACTIVE  = 'inactive'
    STATUS_SUSPENDED = 'suspended'
    STATUS_CHOICES = [
        (STATUS_ACTIVE,    'فعال — ورود و عملیات مجاز'),
        (STATUS_INACTIVE,  'غیرفعال — ورود مجاز، عملیات ممنوع'),
        (STATUS_SUSPENDED, 'معلق — ورود ممنوع'),
    ]

    name = models.CharField('نام سازمان / طرف حساب', max_length=120, unique=True)
    description = models.CharField('توضیحات', max_length=255, blank=True)
    first_name = models.CharField('نام', max_length=60, blank=True)
    last_name = models.CharField('نام خانوادگی', max_length=60, blank=True)
    phone = models.CharField('شماره تماس', max_length=20, blank=True)
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='counterparty_account',
        verbose_name='حساب کاربری ورود',
        help_text='کاربری که به نام این طرف حساب وارد سیستم می‌شود',
    )
    status = models.CharField(
        'وضعیت', max_length=20,
        choices=STATUS_CHOICES, default=STATUS_ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # اگر وضعیت «معلق» شد → حساب کاربری را غیرفعال کن
        # در غیر این صورت → فعال نگه‌دار
        if self.user_id:
            should_be_active = (self.status != self.STATUS_SUSPENDED)
            if self.user.is_active != should_be_active:
                self.user.is_active = should_be_active
                self.user.save(update_fields=['is_active'])
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('رکوردهای طرف حساب دائمی هستند و امکان حذف آن‌ها وجود ندارد.')

    @property
    def can_operate(self):
        """آیا طرف حساب می‌تواند عملیات (تایید) انجام دهد؟"""
        return self.status == self.STATUS_ACTIVE


class CounterpartyBankAccount(models.Model):
    counterparty = models.ForeignKey(
        Counterparty, on_delete=models.CASCADE,
        related_name='bank_accounts',
        verbose_name='طرف حساب',
    )
    bank_name = models.CharField('نام بانک', max_length=80, blank=True)
    city = models.CharField('شهر', max_length=60, blank=True)
    branch = models.CharField('شعبه', max_length=100, blank=True)
    account_number = models.CharField('شماره حساب', max_length=30, blank=True)
    account_owner = models.CharField('نام صاحب حساب', max_length=120, blank=True)
    iban = models.CharField('شماره شبا', max_length=30, blank=True,
                            help_text='IR + 24 رقم')
    is_primary = models.BooleanField('حساب اصلی', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'bank_name']
        verbose_name = 'حساب بانکی طرف حساب'
        verbose_name_plural = 'حساب‌های بانکی طرف حساب'

    def __str__(self):
        parts = [self.bank_name or '', self.account_number or '']
        return ' — '.join(p for p in parts if p)

    def save(self, *args, **kwargs):
        # اگر این حساب را اصلی کردیم، بقیه را غیراصلی کن
        if self.is_primary:
            CounterpartyBankAccount.objects.filter(
                counterparty=self.counterparty
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class LoginAdvertisement(models.Model):
    SLOT_1 = 1
    SLOT_2 = 2
    SLOT_3 = 3
    SLOT_4 = 4
    SLOT_CHOICES = (
        (SLOT_1, 'کادر 1'),
        (SLOT_2, 'کادر 2'),
        (SLOT_3, 'کادر 3'),
        (SLOT_4, 'کادر 4'),
    )

    slot = models.PositiveSmallIntegerField('جایگاه', choices=SLOT_CHOICES, unique=True)
    title = models.CharField('عنوان آگهی', max_length=120)
    description = models.TextField('متن آگهی', blank=True)
    image = models.ImageField('تصویر بنر', upload_to=login_ad_upload_to, blank=True, null=True)
    link_url = models.URLField('لینک مقصد', blank=True)
    start_date = models.DateField('تاریخ شروع')
    end_date = models.DateField('تاریخ خاتمه')
    is_visible = models.BooleanField('نمایش', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slot']
        verbose_name = 'آگهی صفحه ورود'
        verbose_name_plural = 'آگهی های صفحه ورود'

    def __str__(self):
        return f"کادر {self.slot} - {self.title}"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'تاریخ خاتمه باید بعد از تاریخ شروع باشد.'})


class FieldRequirementConfig(models.Model):
    FORM_PAYMENT          = 'payment'
    FORM_ORDER            = 'order'
    FORM_ORDER_ITEM       = 'order_item'
    FORM_PROFILE          = 'profile'
    FORM_PAYMENT_STAFF    = 'payment_staff'
    FORM_PROFORMA         = 'order_proforma'
    FORM_COUNTERPARTY     = 'counterparty'
    FORM_COUNTERPARTY_BANK = 'counterparty_bank'

    FORM_CHOICES = [
        (FORM_PAYMENT,           'فرم ثبت فیش واریزی'),
        (FORM_ORDER,             'فرم ثبت سفارش'),
        (FORM_ORDER_ITEM,        'فرم اقلام سفارش'),
        (FORM_PROFILE,           'فرم ویرایش مشخصات مشتری'),
        (FORM_PAYMENT_STAFF,     'فرم تکمیل اطلاعات فیش (کارمند)'),
        (FORM_PROFORMA,          'فرم صدور پیش فاکتور'),
        (FORM_COUNTERPARTY,      'فرم طرف حساب'),
        (FORM_COUNTERPARTY_BANK, 'فرم حساب بانکی طرف حساب'),
    ]

    form_name       = models.CharField('فرم', max_length=50, choices=FORM_CHOICES)
    field_name      = models.CharField('نام فنی فیلد', max_length=100)
    field_label     = models.CharField('نام نمایشی فیلد', max_length=200)
    default_required = models.BooleanField('پیشفرض کد', default=False, editable=False,
                                           help_text='مقدار پیشفرض تعریف‌شده در کد — فقط‌خواندنی')
    is_required     = models.BooleanField(
        'تنظیم ادمین',
        null=True, blank=True,
        help_text='خالی = استفاده از پیشفرض | بله = اجباری | خیر = اختیاری',
    )

    @property
    def effective_required(self) -> bool:
        """مقدار واقعی اعمال‌شده: پیشفرض کد اگر ادمین override نکرده."""
        return self.default_required if self.is_required is None else self.is_required

    class Meta:
        unique_together = [('form_name', 'field_name')]
        ordering = ['form_name', 'field_name']
        verbose_name = 'تنظیم اجباری بودن فیلد'
        verbose_name_plural = 'تنظیمات اجباری بودن فیلدها'

    def __str__(self):
        status = 'اجباری' if self.is_required else 'اختیاری'
        return f"{self.get_form_name_display()} — {self.field_label} ({status})"


class UploadSettings(models.Model):
    receipt_max_upload_size_mb = models.PositiveIntegerField(
        'حداکثر حجم هر فایل فیش (مگابایت)',
        default=1,
        validators=[MinValueValidator(1)],
    )
    invoice_max_upload_size_mb = models.PositiveIntegerField(
        'حداکثر حجم فایل فاکتور (مگابایت)',
        default=5,
        validators=[MinValueValidator(1)],
    )
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'تنظیمات بارگذاری فایل'
        verbose_name_plural = 'تنظیمات بارگذاری فایل'

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('تنظیمات بارگذاری فایل قابل حذف نیست.')

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def receipt_max_upload_size_bytes(self):
        return self.receipt_max_upload_size_mb * 1024 * 1024

    @property
    def invoice_max_upload_size_bytes(self):
        return self.invoice_max_upload_size_mb * 1024 * 1024

    def __str__(self):
        return 'تنظیمات بارگذاری فایل'


class PaymentRecord(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_COMMERCIAL_REVIEW = 'commercial_review'
    STATUS_TEMP_COMMERCIAL = 'temp_commercial'
    STATUS_APPROVED = 'approved'
    STATUS_FINAL_APPROVED = 'final_approved'
    STATUS_REJECTED = 'rejected'
    STATUS_INCOMPLETE = 'incomplete'
    STATUS_RETURNED_TO_COMMERCIAL = 'returned_commercial'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'در حال بررسی'),
        (STATUS_COMMERCIAL_REVIEW, 'بررسی بازرگانی'),
        (STATUS_TEMP_COMMERCIAL, 'ثبت موقت بازرگانی'),
        (STATUS_APPROVED, 'ثبت بازرگانی'),
        (STATUS_FINAL_APPROVED, 'تایید نهایی'),
        (STATUS_REJECTED, 'رد شده'),
        (STATUS_INCOMPLETE, 'ناقص'),
        (STATUS_RETURNED_TO_COMMERCIAL, 'عودت به بازرگانی'),
    ]

    STAFF_FILTER_COMMERCIAL_APPROVED_FINANCE_PENDING = 'commercial_approved_finance_pending'
    STAFF_FILTER_FINANCE_PENDING = 'finance_pending'

    # گزینه‌های فیلتر اضافی برای پنل کارکنان (شامل فلگ مستقل مالی)
    STAFF_FILTER_CHOICES = STATUS_CHOICES + [
        ('finance_ok', 'ثبت مالی'),
        (STAFF_FILTER_FINANCE_PENDING, 'در انتظار ثبت مالی'),
        (STAFF_FILTER_COMMERCIAL_APPROVED_FINANCE_PENDING, 'ثبت بازرگانی / در بررسی مالی'),
    ]

    CUSTOMER_VISIBLE_LABELS = {
        STATUS_PENDING: 'در حال بررسی',
        STATUS_COMMERCIAL_REVIEW: 'در حال بررسی',
        STATUS_TEMP_COMMERCIAL: 'در حال بررسی',
        STATUS_RETURNED_TO_COMMERCIAL: 'در حال بررسی',
        STATUS_APPROVED: 'ثبت بازرگانی',
        STATUS_FINAL_APPROVED: 'تایید نهایی',
        STATUS_REJECTED: 'رد شده',
        STATUS_INCOMPLETE: 'ناقص',
    }

    # ─── دلیل رد فیش/سند — برای دسته‌بندی و جستجوی فیش‌های رد شده ──────────
    REJECTION_REASON_AMOUNT_MISMATCH = 'amount_mismatch'
    REJECTION_REASON_INVALID_DOCUMENT = 'invalid_document'
    REJECTION_REASON_WRONG_ACCOUNT = 'wrong_account'
    REJECTION_REASON_DUPLICATE = 'duplicate'
    REJECTION_REASON_DEFECTIVE_DOCUMENT = 'defective_document'
    REJECTION_REASON_OTHER = 'other'

    REJECTION_REASON_CHOICES = [
        (REJECTION_REASON_AMOUNT_MISMATCH, 'مغایرت مبلغ'),
        (REJECTION_REASON_INVALID_DOCUMENT, 'فیش/سند نامعتبر یا ناخوانا'),
        (REJECTION_REASON_WRONG_ACCOUNT, 'واریز به حساب اشتباه'),
        (REJECTION_REASON_DUPLICATE, 'تکراری بودن فیش'),
        (REJECTION_REASON_DEFECTIVE_DOCUMENT, 'مخدوش بودن سند'),
        (REJECTION_REASON_OTHER, 'سایر'),
    ]

    # ─── فلگ مالی — مستقل از فلگ بازرگانی ──────────────────────────────────
    FINANCE_STATUS_PENDING  = None           # در انتظار ثبت مالی
    FINANCE_STATUS_APPROVED = 'finance_ok'   # ثبت مالی

    finance_status = models.CharField(
        'وضعیت مالی', max_length=20,
        null=True, blank=True, db_index=True,
    )
    finance_registered_at = models.DateTimeField('زمان ثبت مالی', null=True, blank=True)
    finance_registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='finance_registrations',
        verbose_name='ثبت‌کننده مالی',
    )

    @property
    def is_finance_registered(self):
        return self.finance_status == self.FINANCE_STATUS_APPROVED

    # (تفویض جهانی از طریق FinalApprovalDelegate مدیریت می‌شود)

    @property
    def ready_for_final_approval(self):
        """
        شرایط تأیید نهایی:
        ۱. بازرگانی ثبت کرده (status == approved)
        ۲. مالی ثبت کرده (finance_status == finance_ok)
        ۳. اگر طرف حساب دارد → طرف حساب هم تأیید کرده باشد
        """
        return (
            self.status == self.STATUS_APPROVED
            and self.is_finance_registered
            and (self.counterparty_id is None or self.is_counterparty_approved)
        )

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    counterparty = models.ForeignKey(Counterparty, on_delete=models.PROTECT, null=True, blank=True, related_name='payments')
    first_name = models.CharField(max_length=50, blank=True, default='')
    last_name = models.CharField(max_length=50, blank=True, default='')
    organization = models.CharField(max_length=100, blank=True, default='')
    city = models.CharField(max_length=50, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    amount = models.BigIntegerField(blank=True, null=True)
    pay_date = jmodels.jDateField(verbose_name='تاریخ واریز', blank=True, null=True)
    tracking_code = models.CharField(max_length=50, blank=True, null=True, verbose_name='کد پیگیری')
    payer_account_number = models.CharField(max_length=64, blank=True, default='')
    payer_full_name = models.CharField(max_length=128, blank=True, default='')
    payer_bank_name = models.CharField(max_length=64, blank=True, default='')
    beneficiary_bank_name = models.CharField(max_length=64, blank=True, default='')
    beneficiary_account_number = models.CharField(max_length=64, blank=True, default='')
    beneficiary_account_owner = models.CharField(max_length=128, blank=True, default='')
    receipt_image = models.ImageField(upload_to=payment_record_receipt_upload_to, blank=True, null=True)
    daily_assignment = models.ForeignKey('DailyPaymentAssignment', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    is_locked = models.BooleanField('قفل پایانی', default=False)
    pending_final_approval = models.BooleanField('در انتظار تأیید نهایی', default=False, db_index=True)
    pending_final_approval_since = models.DateTimeField('زمان آماده‌شدن برای تأیید نهایی', null=True, blank=True)
    last_staff_note = models.TextField('آخرین توضیح کارشناس', blank=True)
    rejection_reason = models.CharField(
        'دلیل رد', max_length=30,
        choices=REJECTION_REASON_CHOICES, blank=True, db_index=True,
    )
    customer_notes = models.TextField('توضیحات مشتری', blank=True, help_text='توضیحات یا نکات مشتری در مورد این واریزی')
    created_at    = models.DateTimeField(auto_now_add=True)
    last_edited_at = models.DateTimeField('آخرین ویرایش', null=True, blank=True)
    customer_seen_at = models.DateTimeField('زمان مشاهده مشتری', null=True, blank=True)

    # تصمیم طرف حساب روی فیش
    CP_STATUS_APPROVED = 'cp_approved'
    CP_STATUS_RETURNED = 'cp_returned'
    CP_STATUS_REJECTED = 'cp_rejected'
    CP_STATUS_CHOICES = [
        (CP_STATUS_APPROVED, 'تایید شده'),
        (CP_STATUS_RETURNED, 'عودت / ناقص'),
        (CP_STATUS_REJECTED, 'رد / ابطال'),
    ]

    counterparty_status = models.CharField(
        'وضعیت طرف حساب', max_length=20,
        choices=CP_STATUS_CHOICES, null=True, blank=True, db_index=True,
    )
    counterparty_note = models.TextField('توضیح طرف حساب', blank=True)
    counterparty_decided_at = models.DateTimeField('زمان تصمیم طرف حساب', null=True, blank=True)
    counterparty_decided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='counterparty_decisions',
        verbose_name='تصمیم‌گیرنده طرف حساب',
    )
    @property
    def is_counterparty_approved(self):
        return self.counterparty_status == self.CP_STATUS_APPROVED

    @property
    def is_counterparty_returned(self):
        return self.counterparty_status == self.CP_STATUS_RETURNED

    @property
    def is_counterparty_rejected(self):
        return self.counterparty_status == self.CP_STATUS_REJECTED

    @property
    def counterparty_decided(self):
        return self.counterparty_status is not None

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.amount}"

    @property
    def customer_status_label(self):
        return self.CUSTOMER_VISIBLE_LABELS.get(self.status, 'در حال بررسی')

    # ─── فلگ بازرگانی / فروش ────────────────────────────────────────────────

    @property
    def commercial_status_label(self):
        """عنوان فلگ بازرگانی / فروش بر اساس وضعیت سند."""
        if self.status == self.STATUS_PENDING:
            return 'بررسی بازرگانی'
        if self.status == self.STATUS_COMMERCIAL_REVIEW:
            return 'بررسی بازرگانی'
        if self.status == self.STATUS_APPROVED:
            return 'ثبت بازرگانی'
        if self.status == self.STATUS_FINAL_APPROVED:
            return 'تأیید نهایی'
        if self.status == self.STATUS_RETURNED_TO_COMMERCIAL:
            return 'عودت به بازرگانی'
        if self.status == self.STATUS_REJECTED:
            return 'رد شده'
        if self.status == self.STATUS_INCOMPLETE:
            return 'ناقص'
        return self.get_status_display()

    @property
    def commercial_flag_class(self):
        """رنگ فلگ بازرگانی / فروش."""
        if self.status == self.STATUS_PENDING:
            return 'flag-gray'      # خاکستری — بررسی اولیه
        if self.status == self.STATUS_COMMERCIAL_REVIEW:
            return 'flag-blue'      # آبی — در حال بررسی
        if self.status == self.STATUS_TEMP_COMMERCIAL:
            return 'flag-teal'      # فیروزه‌ای — ثبت موقت بازرگانی
        if self.status == self.STATUS_APPROVED:
            return 'flag-orange'    # نارنجی — ثبت بازرگانی
        if self.status == self.STATUS_FINAL_APPROVED:
            return 'flag-green'     # سبز — تأیید نهایی
        if self.status == self.STATUS_RETURNED_TO_COMMERCIAL:
            return 'flag-purple'    # بنفش کم‌رنگ — عودت
        if self.status == self.STATUS_REJECTED:
            return 'flag-red'       # قرمز
        if self.status == self.STATUS_INCOMPLETE:
            return 'flag-yellow'    # زرد
        return 'flag-gray'

    # ─── فلگ مالی — مستقل ──────────────────────────────────────────────────

    @property
    def finance_status_label(self):
        """عنوان فلگ مالی — مستقل از فلگ بازرگانی."""
        if self.status == self.STATUS_FINAL_APPROVED:
            return 'تأیید نهایی'
        if self.status in {self.STATUS_REJECTED}:
            return 'رد شده'
        if self.status == self.STATUS_INCOMPLETE:
            return 'ناقص — قفل'
        if self.is_finance_registered:
            return 'ثبت مالی'
        return 'در انتظار ثبت مالی'

    @property
    def finance_flag_class(self):
        """رنگ فلگ مالی."""
        if self.status == self.STATUS_FINAL_APPROVED:
            return 'flag-green'     # سبز — تأیید نهایی
        if self.status == self.STATUS_REJECTED:
            return 'flag-red'
        if self.status == self.STATUS_INCOMPLETE:
            return 'flag-yellow'
        if self.is_finance_registered:
            return 'flag-purple'    # بنفش — ثبت مالی
        return 'flag-gray'          # خاکستری — در انتظار

    @property
    def status_flag_class(self):
        return {
            self.STATUS_COMMERCIAL_REVIEW: 'flag-blue',
            self.STATUS_APPROVED: 'flag-orange',
            self.STATUS_FINAL_APPROVED: 'flag-green',
            self.STATUS_REJECTED: 'flag-red',
            self.STATUS_INCOMPLETE: 'flag-yellow',
            self.STATUS_RETURNED_TO_COMMERCIAL: 'flag-gray',
        }.get(self.status, 'flag-gray')

    @property
    def customer_flag_class(self):
        if self.status in {self.STATUS_PENDING, self.STATUS_COMMERCIAL_REVIEW, self.STATUS_RETURNED_TO_COMMERCIAL}:
            return 'flag-gray'
        if self.status == self.STATUS_APPROVED:
            return 'flag-orange'
        if self.status == self.STATUS_FINAL_APPROVED:
            return 'flag-green'
        if self.status == self.STATUS_REJECTED:
            return 'flag-red'
        if self.status == self.STATUS_INCOMPLETE:
            return 'flag-yellow'
        return 'flag-gray'

    @property
    def is_seen_by_customer(self):
        return bool(self.customer_seen_at)


class UserProfile(models.Model):
    ROLE_CHOICES = (
        # گروه مشتریان
        ('customer',          'مشتری'),
        # گروه کارکنان
        ('commercial',        'واحد بازرگانی'),
        ('commercial_manager','مدیر بازرگانی'),
        ('finance',           'واحد مالی'),
        ('finance_manager',   'مدیر مالی'),
        ('sales',             'فروش'),
        ('sales_manager',     'مدیر فروش'),
        ('data_entry',        'تکمیل اطلاعات فیش'),
        ('staff',             'کارمند'),
        ('warranty',          'کارشناس گارانتی'),
        ('warranty_manager',  'مدیر گارانتی'),
        # گروه طرف حساب‌ها
        ('counterparty',      'طرف حساب'),
    )
    AVATAR_PRESET_CHOICES = (
        ('neutral_1', 'نمایه عمومی ۱'),
        ('neutral_2', 'نمایه عمومی ۲'),
        ('male_1', 'نمایه مرد ۱'),
        ('male_2', 'نمایه مرد ۲'),
        ('female_1', 'نمایه زن ۱'),
        ('female_2', 'نمایه زن ۲'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField('نام', max_length=50, blank=True)
    last_name = models.CharField('نام خانوادگی', max_length=50, blank=True)
    phone = models.CharField('شماره تلفن', max_length=20, blank=True)
    mobile = models.CharField('شماره همراه', max_length=20, blank=True)
    second_mobile = models.CharField('شماره همراه دوم', max_length=20, blank=True)
    representative_name = models.CharField('نام نماینده', max_length=100, blank=True)
    representative_mobile = models.CharField('موبایل نماینده', max_length=20, blank=True)
    delegate_sms_to_representative = models.BooleanField('ارسال پیامک به نماینده', default=False)
    organization = models.CharField('نام مجموعه', max_length=100, blank=True)
    city = models.CharField('شهر', max_length=50, blank=True)
    province = models.CharField('استان', max_length=50, blank=True)
    address = models.TextField('آدرس', blank=True)
    second_address = models.TextField('آدرس دوم', blank=True)
    role = models.CharField('نوع کاربر', max_length=24, choices=ROLE_CHOICES, default='customer')
    active_from = jmodels.jDateField('تاریخ آغاز فعالیت', null=True, blank=True)
    valid_until = jmodels.jDateField('تاریخ اعتبار', null=True, blank=True)
    force_password_change = models.BooleanField('الزام تعویض رمز', default=True)
    suspended = models.BooleanField('معلق', default=False)
    can_view_invoices = models.BooleanField('دسترسی مشاهده فاکتورها', default=False)
    can_upload_invoices = models.BooleanField('دسترسی بارگذاری فاکتورها', default=False)
    can_edit_payment_details = models.BooleanField('دسترسی تکمیل اطلاعات فیش‌ها', default=False)
    can_access_reconciliation = models.BooleanField('دسترسی مغایرت‌گیری', default=False)
    accounting_code = models.CharField('کد تفضیلی', max_length=50, blank=True)
    sms_mfa_enabled = models.BooleanField('ورود دو مرحله‌ای با پیامک', default=False)
    avatar_image = models.ImageField('عکس نمایه', upload_to=profile_avatar_upload_to, blank=True, null=True)
    avatar_preset = models.CharField('نمایه پیش‌فرض', max_length=20, choices=AVATAR_PRESET_CHOICES, default='neutral_1')

    def __str__(self):
        return self.user.username

    @property
    def display_name(self):
        full_name = f"{self.user.first_name} {self.user.last_name}".strip()
        if not full_name:
            full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.user.username

    @property
    def sms_number(self):
        """شماره برای ارسال پیامک — موبایل اول، در غیر این‌صورت شماره تلفن."""
        if self.delegate_sms_to_representative and self.representative_mobile:
            return self.representative_mobile.strip()
        return (self.mobile or self.phone or '').strip()

    @property
    def avatar_url(self):
        if self.avatar_image:
            try:
                return self.avatar_image.url
            except ValueError:
                return ''
        return ''

    @property
    def avatar_icon(self):
        return {
            'neutral_1': '👤',
            'neutral_2': '◉',
            'male_1': '👨',
            'male_2': '♂',
            'female_1': '👩',
            'female_2': '♀',
        }.get(self.avatar_preset, '👤')

    @property
    def avatar_class(self):
        return f"avatar-{self.avatar_preset or 'neutral_1'}"


class ReconciliationThread(models.Model):
    STATUS_OPEN = 'open'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = (
        (STATUS_OPEN, 'باز'),
        (STATUS_CLOSED, 'بسته'),
    )

    DOC_PAYMENT = 'payment'
    DOC_ORDER = 'order'
    DOC_PROFORMA = 'proforma'
    DOC_INVOICE = 'invoice'
    DOC_DAILY_PAYMENT = 'daily_payment'
    DOC_OTHER = 'other'
    DOCUMENT_CHOICES = (
        (DOC_PAYMENT, 'فیش واریزی'),
        (DOC_ORDER, 'سفارش'),
        (DOC_PROFORMA, 'پیشنهاد فروش / پیش‌فاکتور'),
        (DOC_INVOICE, 'فاکتور فروش'),
        (DOC_DAILY_PAYMENT, 'برنامه واریز'),
        (DOC_OTHER, 'سایر'),
    )

    title = models.CharField('عنوان گفتگو', max_length=160)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reconciliation_threads', verbose_name='مشتری')
    staff_participants = models.ManyToManyField(User, related_name='assigned_reconciliation_threads', verbose_name='کارشناسان منتخب')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_reconciliation_threads', verbose_name='ایجادکننده')
    status = models.CharField('وضعیت', max_length=12, choices=STATUS_CHOICES, default=STATUS_OPEN)
    document_type = models.CharField('نوع سند مرجع', max_length=24, choices=DOCUMENT_CHOICES, default=DOC_OTHER, blank=True)
    document_id = models.PositiveIntegerField('شناسه سند مرجع', null=True, blank=True)
    created_at = models.DateTimeField('زمان ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        verbose_name = 'گفتگوی مغایرت‌گیری'
        verbose_name_plural = 'گفتگوهای مغایرت‌گیری'

    def __str__(self):
        return self.title

    @property
    def document_label(self):
        if not self.document_type or self.document_type == self.DOC_OTHER:
            return ''
        return f'{self.get_document_type_display()} #{self.document_id or "-"}'


class ReconciliationMessage(models.Model):
    thread = models.ForeignKey(ReconciliationThread, on_delete=models.CASCADE, related_name='messages', verbose_name='گفتگو')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciliation_messages', verbose_name='فرستنده')
    body = models.TextField('متن پیام', blank=True)
    attachment = models.FileField('فایل پیوست', upload_to=reconciliation_attachment_upload_to, null=True, blank=True)
    attachment_name = models.CharField('نام فایل پیوست', max_length=255, blank=True)
    document_type = models.CharField('نوع سند ارجاع‌شده', max_length=24, choices=ReconciliationThread.DOCUMENT_CHOICES, default='', blank=True)
    document_id = models.PositiveIntegerField('شناسه سند ارجاع‌شده', null=True, blank=True)
    created_at = models.DateTimeField('زمان ارسال', auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'پیام مغایرت‌گیری'
        verbose_name_plural = 'پیام‌های مغایرت‌گیری'

    def __str__(self):
        return f'{self.thread_id} - {self.sender}'

    @property
    def document_label(self):
        if not self.document_type:
            return ''
        return f'{self.get_document_type_display()} #{self.document_id or "-"}'

    @property
    def attachment_display_name(self):
        if not self.attachment:
            return ''
        return self.attachment_name or self.attachment.name.rsplit('/', 1)[-1]


class ReconciliationReadState(models.Model):
    thread = models.ForeignKey(ReconciliationThread, on_delete=models.CASCADE, related_name='read_states', verbose_name='گفتگو')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reconciliation_read_states', verbose_name='کاربر')
    last_read_at = models.DateTimeField('آخرین زمان خواندن', default=timezone.now)

    class Meta:
        unique_together = [('thread', 'user')]
        verbose_name = 'وضعیت خواندن مغایرت‌گیری'
        verbose_name_plural = 'وضعیت خواندن مغایرت‌گیری'

    def __str__(self):
        return f'{self.thread_id} - {self.user}'


class ProfileChangeRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'در انتظار تایید'),
        (STATUS_APPROVED, 'تایید شده'),
        (STATUS_REJECTED, 'رد شده'),
    ]

    FIELD_LABELS = {
        'email': 'ایمیل',
        'phone': 'شماره تلفن',
        'second_mobile': 'شماره همراه دوم',
        'representative_name': 'نام نماینده',
        'representative_mobile': 'موبایل نماینده',
        'delegate_sms_to_representative': 'ارسال پیامک به نماینده',
        'organization': 'نام مجموعه',
        'address': 'آدرس',
        'second_address': 'آدرس دوم',
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_change_requests')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_profile_changes')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_profile_changes')
    changes = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"

    @property
    def change_items(self):
        items = []
        for field_name, values in (self.changes or {}).items():
            old_value = (values or {}).get('old')
            new_value = (values or {}).get('new')
            if field_name == 'delegate_sms_to_representative':
                old_value = 'بله' if bool(old_value) else 'خیر'
                new_value = 'بله' if bool(new_value) else 'خیر'
            items.append({
                'field': field_name,
                'label': self.FIELD_LABELS.get(field_name, field_name),
                'old': old_value or '-',
                'new': new_value or '-',
            })
        return items

    def apply_changes(self, reviewer):
        profile = self.user.profile
        update_profile_fields = []
        update_user_fields = []
        for field_name, values in (self.changes or {}).items():
            new_value = (values or {}).get('new') or ''
            if field_name == 'email':
                self.user.email = new_value
                update_user_fields.append('email')
            elif hasattr(profile, field_name):
                setattr(profile, field_name, new_value)
                update_profile_fields.append(field_name)
        if update_user_fields:
            self.user.save(update_fields=sorted(set(update_user_fields)))
        if update_profile_fields:
            profile.save(update_fields=sorted(set(update_profile_fields)))
        self.status = self.STATUS_APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])


class PaymentReceipt(models.Model):
    payment = models.ForeignKey(PaymentRecord, on_delete=models.CASCADE, related_name='receipts')
    image = models.FileField(upload_to=payment_receipt_upload_to)
    file_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['payment', 'file_hash'], name='uniq_payment_receipt_hash'),
        ]


class DailyPaymentPlan(models.Model):
    deposit_date = jmodels.jDateField('تاریخ واریز')
    bank_name = models.CharField('نام بانک', max_length=64, blank=True)
    account_number = models.CharField('شماره حساب مقصد', max_length=64)
    account_owner = models.CharField('نام صاحب حساب', max_length=128, blank=True)
    total_expected_amount = models.BigIntegerField('مبلغ کل مورد انتظار', default=0)
    note = models.TextField('توضیح', blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_daily_payment_plans')
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        ordering = ['-deposit_date', '-id']
        verbose_name = 'برنامه واریز روزانه'
        verbose_name_plural = 'برنامه های واریز روزانه'

    def __str__(self):
        return f"{self.deposit_date} - {self.account_number}"


class DailyPaymentAssignment(models.Model):
    plan = models.ForeignKey(DailyPaymentPlan, on_delete=models.CASCADE, related_name='assignments')
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='daily_payment_assignments')
    expected_amount = models.BigIntegerField('مبلغ مورد انتظار')
    note = models.TextField('توضیح', blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        ordering = ['customer__first_name', 'customer__last_name', 'customer__username']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'customer'], name='uniq_daily_payment_assignment_customer'),
        ]
        verbose_name = 'تخصیص واریز روزانه'
        verbose_name_plural = 'تخصیص های واریز روزانه'

    def __str__(self):
        return f"{self.customer} - {self.expected_amount}"


class PaymentActivityLog(models.Model):
    ACTION_CREATED              = 'created'
    ACTION_EDITED               = 'edited'
    ACTION_STATUS_CHANGED       = 'status_changed'
    ACTION_VIEWED               = 'viewed'
    ACTION_CUSTOMER_NOTE        = 'customer_note'
    ACTION_FINANCE_REGISTERED   = 'finance_reg'
    ACTION_FINAL_APPROVED       = 'final_approved'
    ACTION_CP_APPROVED          = 'cp_approved'
    ACTION_CP_RETURNED          = 'cp_returned'
    ACTION_CP_REJECTED          = 'cp_rejected'

    ACTION_CHOICES = [
        (ACTION_CREATED,          'ثبت سند'),
        (ACTION_EDITED,           'ویرایش سند'),
        (ACTION_STATUS_CHANGED,   'تغییر وضعیت بازرگانی'),
        (ACTION_VIEWED,           'مشاهده'),
        (ACTION_CUSTOMER_NOTE,    'توضیح مشتری'),
        (ACTION_FINANCE_REGISTERED,'ثبت مالی'),
        (ACTION_FINAL_APPROVED,   'تأیید نهایی'),
        (ACTION_CP_APPROVED,      'تایید طرف حساب'),
        (ACTION_CP_RETURNED,      'عودت/ناقص از طرف حساب'),
        (ACTION_CP_REJECTED,      'رد/ابطال توسط طرف حساب'),
    ]

    payment = models.ForeignKey(PaymentRecord, on_delete=models.CASCADE, related_name='activity_logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class SystemActivityLog(models.Model):
    ACTION_USER_CREATED = 'user_created'
    ACTION_USER_UPDATED = 'user_updated'
    ACTION_PASSWORD_RESET = 'password_reset'
    ACTION_PROFILE_UPDATED = 'profile_updated'

    ACTION_CHOICES = [
        (ACTION_USER_CREATED, 'ایجاد کاربر'),
        (ACTION_USER_UPDATED, 'ویرایش کاربر'),
        (ACTION_PASSWORD_RESET, 'ریست رمز عبور'),
        (ACTION_PROFILE_UPDATED, 'ویرایش مشخصات کاربر'),
    ]

    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_system_logs')
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='targeted_system_logs')
    action = models.CharField('عملیات', max_length=40, choices=ACTION_CHOICES)
    description = models.TextField('توضیحات', blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'لاگ عملیات سیستم'
        verbose_name_plural = 'لاگ‌های عملیات سیستم'

    def __str__(self):
        target = self.target_user.username if self.target_user else '-'
        return f"{self.get_action_display()} - {target}"


class UserNotification(models.Model):
    CATEGORY_PAYMENT = 'payment'
    CATEGORY_INVOICE = 'invoice'
    CATEGORY_SYSTEM = 'system'

    CATEGORY_CHOICES = [
        (CATEGORY_PAYMENT, 'فیش واریزی'),
        (CATEGORY_INVOICE, 'فاکتور'),
        (CATEGORY_SYSTEM, 'سیستم'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    title = models.CharField('عنوان', max_length=120)
    message = models.TextField('متن اعلان')
    url = models.CharField('آدرس', max_length=255, blank=True)
    category = models.CharField('نوع', max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_SYSTEM)
    is_read = models.BooleanField('خوانده شده', default=False)
    created_at = models.DateTimeField('زمان ایجاد', auto_now_add=True)
    read_at = models.DateTimeField('زمان خواندن', null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]
        verbose_name = 'اعلان کاربر'
        verbose_name_plural = 'اعلان‌های کاربران'

    def __str__(self):
        return f"{self.user} - {self.title}"

    @property
    def resolved_url(self):
        url = self.url or reverse('submit')
        if url == reverse('submit') and 'طرف حساب' in (self.title or ''):
            match = re.search(r'#(\d+)', self.message or '')
            if match:
                return reverse('payment_timeline', args=[int(match.group(1))])
        return url


class InvoiceRecord(models.Model):
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='invoice_records')
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_invoice_records',
    )
    amount = models.BigIntegerField('مبلغ', null=True, blank=True)
    invoice_date = jmodels.jDateField('تاریخ فاکتور', null=True, blank=True)
    invoice_number = models.CharField('شماره فاکتور', max_length=80, blank=True)
    reference_number = models.CharField('شماره حواله', max_length=80, blank=True)
    attachment = models.FileField('فایل فاکتور', upload_to=invoice_attachment_upload_to)
    customer_visible_note = models.TextField('توضیحات قابل مشاهده برای مشتری', blank=True)
    internal_note = models.TextField('توضیحات داخلی', blank=True)
    customer_note = models.TextField('یادداشت مشتری', blank=True)
    customer_note_updated_at = models.DateTimeField('آخرین بروزرسانی یادداشت', null=True, blank=True)
    customer_seen_at = models.DateTimeField('زمان مشاهده مشتری', null=True, blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'فاکتور مشتری'
        verbose_name_plural = 'فاکتورهای مشتری'

    def __str__(self):
        return f"فاکتور {self.invoice_number} - {self.customer.username}"

    @property
    def is_seen_by_customer(self):
        return bool(self.customer_seen_at)


class InvoiceExtractionJob(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'در انتظار پردازش'),
        (STATUS_PROCESSING, 'در حال پردازش'),
        (STATUS_DONE, 'پردازش شده'),
        (STATUS_FAILED, 'ناموفق'),
    ]

    SOURCE_PREVIEW = 'preview'
    SOURCE_INVOICE = 'invoice'

    SOURCE_CHOICES = [
        (SOURCE_PREVIEW, 'پیش نمایش فرم'),
        (SOURCE_INVOICE, 'فاکتور ثبت شده'),
    ]

    invoice = models.ForeignKey(
        InvoiceRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='extraction_jobs',
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_extraction_jobs',
    )
    source = models.CharField('منبع', max_length=20, choices=SOURCE_CHOICES, default=SOURCE_PREVIEW)
    file = models.FileField('فایل پردازش', upload_to=invoice_extraction_upload_to)
    original_filename = models.CharField('نام فایل اصلی', max_length=255, blank=True)
    file_kind = models.CharField('نوع فایل', max_length=30, blank=True)
    text_source = models.CharField('منبع متن', max_length=30, blank=True)
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    result_json = models.JSONField('خروجی JSON', default=dict, blank=True)
    raw_text = models.TextField('متن خام استخراج شده', blank=True)
    warnings = models.JSONField('هشدارها', default=list, blank=True)
    error_message = models.TextField('خطا', blank=True)
    created_at = models.DateTimeField('زمان ایجاد', auto_now_add=True)
    started_at = models.DateTimeField('زمان شروع', null=True, blank=True)
    finished_at = models.DateTimeField('زمان پایان', null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'پردازش خواندن فاکتور'
        verbose_name_plural = 'پردازش‌های خواندن فاکتور'

    def __str__(self):
        return f"{self.original_filename or self.file.name} - {self.status}"


class PriceList(models.Model):
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='price_lists')
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_price_lists',
    )
    title = models.CharField('عنوان', max_length=120, blank=True)
    file = models.FileField('فایل لیست قیمت', upload_to=price_list_upload_to)
    batch_id = models.UUIDField('شناسه بسته ارسال', default=uuid.uuid4, db_index=True)
    customer_seen_at = models.DateTimeField('زمان مشاهده مشتری', null=True, blank=True)
    note = models.TextField('توضیحات داخلی', blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'لیست قیمت'
        verbose_name_plural = 'لیست قیمت‌ها'

    def __str__(self):
        return f"{self.customer.username} - {self.title or self.file.name}"

    @property
    def is_seen_by_customer(self):
        return bool(self.customer_seen_at)


class ProformaInvoice(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'در انتظار تایید مشتری'),
        (STATUS_APPROVED, 'تایید شده توسط مشتری'),
    ]

    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='proforma_invoices')
    order = models.ForeignKey(
        'CustomerOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='proformas',
        verbose_name='سفارش مرتبط',
    )
    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_proforma_invoices',
    )
    title = models.CharField('عنوان', max_length=120, blank=True)
    valid_until = jmodels.jDateField('اعتبار تا')
    file = models.FileField('فایل پیش فاکتور', upload_to=proforma_upload_to)
    note = models.TextField('توضیحات داخلی', blank=True)
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    customer_seen_at = models.DateTimeField('زمان مشاهده مشتری', null=True, blank=True)
    approved_at = models.DateTimeField('زمان تایید مشتری', null=True, blank=True)
    created_at = models.DateTimeField('زمان صدور', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'پیش فاکتور'
        verbose_name_plural = 'پیش فاکتورها'

    def __str__(self):
        return f"{self.customer.username} - {self.title or self.file.name}"

    @property
    def is_approved(self):
        return self.status == self.STATUS_APPROVED

    @property
    def is_seen_by_customer(self):
        return bool(self.customer_seen_at)


class CustomerSalesAssignment(models.Model):
    customer = models.OneToOneField(User, on_delete=models.CASCADE, related_name='sales_assignment')
    sales_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_customers',
        verbose_name='کارشناس فروش',
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_assignments_made',
        verbose_name='تخصیص دهنده',
    )
    note = models.TextField('توضیح', blank=True)
    created_at = models.DateTimeField('زمان ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        ordering = ['customer__username']
        verbose_name = 'تخصیص کارشناس فروش'
        verbose_name_plural = 'تخصیص کارشناسان فروش'

    def __str__(self):
        return f"{self.customer} -> {self.sales_user or '-'}"


class CustomerOrder(models.Model):
    STATUS_SUBMITTED = 'submitted'
    STATUS_REVIEWING = 'reviewing'
    STATUS_PROFORMA_SENT = 'proforma_sent'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'ثبت شده'),
        (STATUS_REVIEWING, 'در حال بررسی فروش'),
        (STATUS_PROFORMA_SENT, 'پیش فاکتور صادر شده'),
        (STATUS_COMPLETED, 'خاتمه یافته'),
        (STATUS_CANCELLED, 'لغو شده'),
    ]

    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='orders', verbose_name='مشتری')
    sales_expert = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_orders',
        verbose_name='کارشناس فروش',
    )
    requested_sales_expert = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_sales_orders',
        verbose_name='کارشناس فروش انتخابی مشتری',
    )
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    title = models.CharField('عنوان سفارش', max_length=160, blank=True)
    customer_note = models.TextField('توضیح مشتری', blank=True)
    staff_note = models.TextField('توضیح داخلی فروش', blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['sales_expert', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]
        verbose_name = 'سفارش مشتری'
        verbose_name_plural = 'سفارش های مشتریان'

    def __str__(self):
        return f"ORD-{self.id} - {self.customer}"

    @property
    def order_number(self):
        return f"ORD-{self.id:05d}"

    @property
    def item_summary(self):
        names = [item.product_name for item in self.items.all()[:3]]
        return '، '.join(names)


class ProductCatalog(models.Model):
    product_name = models.CharField('نام کالا', max_length=200)
    product_code = models.CharField('کد کالا', max_length=50, blank=True)
    unit = models.CharField('واحد', max_length=50, blank=True)
    coefficient = models.DecimalField('ضریب', max_digits=12, decimal_places=4, null=True, blank=True)
    is_active = models.BooleanField('فعال', default=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)

    class Meta:
        ordering = ['product_name']
        verbose_name = 'کالا'
        verbose_name_plural = 'کاتالوگ کالاها'

    def __str__(self):
        return f"{self.product_name} ({self.product_code})" if self.product_code else self.product_name


class CustomerOrderItem(models.Model):
    order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField('نام کالا', max_length=180)
    quantity = models.DecimalField('تعداد', max_digits=12, decimal_places=2)
    unit = models.CharField('واحد', max_length=50, blank=True, default='')
    note = models.CharField('توضیح', max_length=255, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'قلم سفارش'
        verbose_name_plural = 'اقلام سفارش'

    def __str__(self):
        return f"{self.product_name} - {self.quantity} {self.unit}".strip()


class CustomerOrderLog(models.Model):
    ACTION_CREATED = 'created'
    ACTION_STATUS_CHANGED = 'status_changed'
    ACTION_ASSIGNED = 'assigned'
    ACTION_PROFORMA_CREATED = 'proforma_created'
    ACTION_PROFORMA_APPROVED = 'proforma_approved'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'ثبت سفارش'),
        (ACTION_STATUS_CHANGED, 'تغییر وضعیت'),
        (ACTION_ASSIGNED, 'تخصیص کارشناس'),
        (ACTION_PROFORMA_CREATED, 'صدور پیش فاکتور'),
        (ACTION_PROFORMA_APPROVED, 'تایید پیش فاکتور توسط مشتری'),
    ]

    order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_logs')
    action = models.CharField('عملیات', max_length=30, choices=ACTION_CHOICES)
    from_status = models.CharField('وضعیت قبلی', max_length=20, blank=True)
    to_status = models.CharField('وضعیت جدید', max_length=20, blank=True)
    note = models.TextField('توضیح', blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'لاگ سفارش'
        verbose_name_plural = 'لاگ های سفارش'

    def __str__(self):
        return f"{self.order} - {self.get_action_display()}"


class ProformaInvoiceLog(models.Model):
    ACTION_VIEWED = 'viewed'
    ACTION_FILE_VIEWED = 'file_viewed'
    ACTION_APPROVED = 'approved'

    ACTION_CHOICES = [
        (ACTION_VIEWED, 'مشاهده'),
        (ACTION_FILE_VIEWED, 'مشاهده فایل'),
        (ACTION_APPROVED, 'تایید مشتری'),
    ]

    proforma = models.ForeignKey(ProformaInvoice, on_delete=models.CASCADE, related_name='logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='proforma_logs')
    action = models.CharField('عملیات', max_length=20, choices=ACTION_CHOICES)
    note = models.TextField('توضیح', blank=True)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'لاگ پیش فاکتور'
        verbose_name_plural = 'لاگ‌های پیش فاکتور'


class UserSession(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='active_session',
        verbose_name='کاربر',
    )
    session_key = models.CharField('کلید نشست', max_length=40, db_index=True)
    created_at = models.DateTimeField('زمان ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین به‌روزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'نشست فعال'
        verbose_name_plural = 'نشست‌های فعال'

    def __str__(self):
        return f"{self.user.username} - {self.session_key[:8]}…"


class LoginRecord(models.Model):
    LOGOUT_MANUAL = 'manual'
    LOGOUT_INACTIVITY = 'inactivity'
    LOGOUT_FORCED = 'forced'
    LOGOUT_CHOICES = [
        (LOGOUT_MANUAL, 'خروج دستی'),
        (LOGOUT_INACTIVITY, 'انقضای بی‌فعالیت'),
        (LOGOUT_FORCED, 'ورود از دستگاه دیگر'),
    ]

    DEVICE_DESKTOP = 'desktop'
    DEVICE_MOBILE = 'mobile'
    DEVICE_TABLET = 'tablet'
    DEVICE_BOT = 'bot'
    DEVICE_CHOICES = [
        (DEVICE_DESKTOP, 'رایانه'),
        (DEVICE_MOBILE, 'موبایل'),
        (DEVICE_TABLET, 'تبلت'),
        (DEVICE_BOT, 'ربات'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='login_records', verbose_name='کاربر',
    )
    session_key = models.CharField('کلید نشست', max_length=40, db_index=True)

    # آدرس IP
    ip_address = models.GenericIPAddressField('آدرس IP', null=True, blank=True)
    x_forwarded_for = models.TextField(
        'زنجیره X-Forwarded-For', blank=True,
        help_text='ممکن است شامل آدرس‌های شبکه داخلی باشد',
    )

    # اطلاعات مرورگر
    user_agent_raw = models.TextField('User-Agent خام', blank=True)
    browser_family = models.CharField('مرورگر', max_length=100, blank=True)
    browser_version = models.CharField('نسخه مرورگر', max_length=50, blank=True)

    # اطلاعات سیستم‌عامل
    os_family = models.CharField('سیستم‌عامل', max_length=100, blank=True)
    os_version = models.CharField('نسخه سیستم‌عامل', max_length=50, blank=True)

    # نوع دستگاه
    device_type = models.CharField(
        'نوع دستگاه', max_length=10,
        choices=DEVICE_CHOICES, default=DEVICE_DESKTOP, blank=True,
    )
    device_brand = models.CharField('برند دستگاه', max_length=100, blank=True)
    device_model = models.CharField('مدل دستگاه', max_length=100, blank=True)

    # سایر هدرها
    accept_language = models.CharField('زبان مرورگر', max_length=200, blank=True)

    # زمان‌ها
    login_at = models.DateTimeField('زمان ورود', auto_now_add=True)
    logout_at = models.DateTimeField('زمان خروج', null=True, blank=True)
    logout_reason = models.CharField(
        'دلیل خروج', max_length=20,
        choices=LOGOUT_CHOICES, blank=True,
    )

    class Meta:
        ordering = ['-login_at']
        verbose_name = 'سابقه ورود'
        verbose_name_plural = 'سوابق ورود'

    def __str__(self):
        return f"{self.user.username} — {self.ip_address} — {self.login_at:%Y/%m/%d %H:%M}"


class SystemSettings(models.Model):
    session_inactivity_timeout = models.PositiveIntegerField(
        'مدت بی‌فعالیت (دقیقه)',
        default=15,
        help_text='پس از این مدت بی‌فعالیت، کاربر به‌صورت خودکار خارج می‌شود.',
    )
    system_logo = models.ImageField(
        'لوگوی سامانه',
        upload_to=system_logo_upload_to,
        blank=True,
        null=True,
        help_text='فرمت مجاز: PNG/JPG/WEBP، حداکثر 512KB، حداکثر 600×220 پیکسل.',
    )

    # ─── تنظیمات منو ────────────────────────────────────────────────────────
    customer_warranty_menu_enabled = models.BooleanField(
        'نمایش منوی «گارانتی و خدمات پس از فروش» برای مشتریان',
        default=False,
        help_text='در صورت فعال بودن، گزینه‌های درخواست گارانتی، درخواست‌های من و پیگیری وضعیت در منوی مشتریان نمایش داده می‌شود.',
    )
    accounting_code_import_enabled = models.BooleanField(
        'فعال بودن دکمه «ورود کد تفضیلی از اکسل» در صفحه مشتریان',
        default=False,
        help_text='در صورت غیرفعال بودن، این دکمه برای هیچ‌کس (حتی مدیران) در صفحه مشتریان نمایش داده نمی‌شود.',
    )

    # ─── تنظیمات پیامک ──────────────────────────────────────────────────────
    SMS_PROVIDER_KAVENEGAR = 'kavenegar'
    SMS_PROVIDER_GHASEDAK  = 'ghasedak'
    SMS_PROVIDER_GENERIC   = 'generic'
    SMS_PROVIDER_DISABLED  = 'disabled'
    SMS_PROVIDER_CHOICES = [
        (SMS_PROVIDER_DISABLED,  'غیرفعال'),
        (SMS_PROVIDER_KAVENEGAR, 'کاوه‌نگار (Kavenegar)'),
        (SMS_PROVIDER_GHASEDAK,  'قاصدک (Ghasedak)'),
        (SMS_PROVIDER_GENERIC,   'HTTP عمومی (سایر اپراتورها)'),
    ]

    sms_provider = models.CharField(
        'اپراتور پیامک', max_length=20,
        choices=SMS_PROVIDER_CHOICES, default=SMS_PROVIDER_DISABLED,
    )
    sms_api_key = models.CharField('کلید API پیامک', max_length=256, blank=True)
    sms_sender = models.CharField(
        'شماره فرستنده', max_length=40, blank=True,
        help_text='شماره خط اختصاصی یا نام خط (بسته به اپراتور)',
    )
    sms_generic_url = models.URLField(
        'آدرس API پیامک عمومی', blank=True,
        help_text='فقط برای نوع HTTP عمومی — آدرس endpoint ارسال پیامک',
    )
    sms_generic_extra = models.JSONField(
        'پارامترهای اضافه API', default=dict, blank=True,
        help_text='JSON اضافی که به body درخواست اضافه می‌شود (مثلاً username/password)',
    )
    sms_otp_template = models.CharField(
        'قالب پیام OTP', max_length=200,
        default='کد تأیید سامانه: {code}\nاعتبار: {minutes} دقیقه',
        help_text='متغیرهای مجاز: {code}, {minutes}',
    )
    sms_otp_expiry_minutes = models.PositiveSmallIntegerField('اعتبار کد OTP (دقیقه)', default=5)
    sms_notifications_enabled = models.BooleanField('اطلاع‌رسانی پیامکی فعال', default=False)

    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'تنظیمات سیستم'
        verbose_name_plural = 'تنظیمات سیستم'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('تنظیمات سیستم قابل حذف نیست.')

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'تنظیمات سیستم'

    @property
    def system_logo_url(self):
        if self.system_logo:
            try:
                return self.system_logo.url
            except ValueError:
                return ''
        return ''


class SMSOTPCode(models.Model):
    """کد یک‌بارمصرف ارسال‌شده از طریق پیامک."""

    PURPOSE_MFA       = 'mfa'
    PURPOSE_APPROVAL  = 'approval'
    PURPOSE_CHOICES = [
        (PURPOSE_MFA,      'ورود دو مرحله‌ای'),
        (PURPOSE_APPROVAL, 'تأیید عملیات'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_otps', verbose_name='کاربر')
    phone      = models.CharField('شماره گیرنده', max_length=20)
    code       = models.CharField('کد OTP', max_length=8)
    purpose    = models.CharField('هدف', max_length=20, choices=PURPOSE_CHOICES, default=PURPOSE_MFA)
    ref_id     = models.CharField('شناسه مرجع', max_length=50, blank=True,
                                   help_text='مثلاً شناسه سند برای تأیید از طریق پیامک')
    is_used    = models.BooleanField('مصرف شده', default=False)
    attempts   = models.PositiveSmallIntegerField('تعداد تلاش', default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField('زمان انقضا')

    class Meta:
        verbose_name = 'کد OTP پیامکی'
        verbose_name_plural = 'کدهای OTP پیامکی'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'purpose', 'is_used'])]

    def __str__(self):
        return f'{self.user.username} — {self.phone} — {self.purpose}'

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired and self.attempts < 5


class SMSSendLog(models.Model):
    """لاگ ارسال پیامک‌ها برای مانیتورینگ و حسابرسی."""

    STATUS_SENT    = 'sent'
    STATUS_FAILED  = 'failed'
    STATUS_CHOICES = [(STATUS_SENT, 'ارسال شد'), (STATUS_FAILED, 'خطا')]

    recipient  = models.CharField('گیرنده', max_length=20)
    message    = models.TextField('متن پیام')
    purpose    = models.CharField('هدف', max_length=40, blank=True)
    status     = models.CharField('وضعیت', max_length=10, choices=STATUS_CHOICES)
    provider   = models.CharField('اپراتور', max_length=20, blank=True)
    error      = models.TextField('خطا', blank=True)
    sent_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'لاگ پیامک'
        verbose_name_plural = 'لاگ پیامک‌ها'
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.recipient} — {self.status} — {self.sent_at:%Y/%m/%d %H:%M}'


class FinalApprovalDelegate(models.Model):
    """تفویض اختیار تأیید نهایی — مدیر مالی می‌تواند به کاربران مشخصی این اختیار را بدهد."""
    delegated_user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='final_approval_delegations',
        verbose_name='کاربر تفویض‌شده',
    )
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='granted_delegations',
        verbose_name='تفویض‌کننده',
    )
    is_active = models.BooleanField('فعال', default=True)
    note = models.TextField('توضیح', blank=True)
    created_at = models.DateTimeField('زمان ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        unique_together = [('delegated_user',)]
        verbose_name = 'تفویض تأیید نهایی'
        verbose_name_plural = 'تفویض‌های تأیید نهایی'

    def __str__(self):
        return f"{self.delegated_user.get_full_name() or self.delegated_user.username} ({'فعال' if self.is_active else 'غیرفعال'})"


# ─── پلتفرم درخواست نمایندگی ──────────────────────────────────────────────────

class AgencyApplication(models.Model):
    STATUS_PENDING     = 'pending'
    STATUS_REVIEWING   = 'reviewing'
    STATUS_INFO_NEEDED = 'info_needed'
    STATUS_APPROVED    = 'approved'
    STATUS_REJECTED    = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING,     'در انتظار بررسی'),
        (STATUS_REVIEWING,   'در حال بررسی'),
        (STATUS_INFO_NEEDED, 'نیاز به اطلاعات تکمیلی'),
        (STATUS_APPROVED,    'تأیید شده'),
        (STATUS_REJECTED,    'رد شده'),
    ]

    STATUS_CLASS = {
        STATUS_PENDING:     'flag-gray',
        STATUS_REVIEWING:   'flag-blue',
        STATUS_INFO_NEEDED: 'flag-yellow',
        STATUS_APPROVED:    'flag-green',
        STATUS_REJECTED:    'flag-red',
    }

    # ارتباط
    phone          = models.CharField('شماره موبایل', max_length=20, db_index=True)
    phone_verified = models.BooleanField('موبایل تأیید شده', default=False)
    email          = models.EmailField('ایمیل', blank=True)

    # مشخصات فردی
    first_name  = models.CharField('نام', max_length=50)
    last_name   = models.CharField('نام خانوادگی', max_length=50)
    national_id = models.CharField('کد ملی', max_length=10, blank=True)

    # موقعیت جغرافیایی
    province         = models.CharField('استان', max_length=50)
    city             = models.CharField('شهر', max_length=50)
    home_address     = models.TextField('آدرس محل سکونت')
    business_address = models.TextField('آدرس محل فعالیت')

    # پروفایل کاری
    activity_domain      = models.CharField('حوزه فعالیت', max_length=100)
    services_offered     = models.TextField('خدمات قابل ارائه')
    years_experience     = models.PositiveSmallIntegerField('سابقه کاری (سال)', default=0)
    has_business_license = models.BooleanField('جواز کسب دارم', default=False)

    # معرف
    referrer_name  = models.CharField('نام معرف', max_length=100, blank=True)
    referrer_phone = models.CharField('موبایل معرف', max_length=20, blank=True)

    # انگیزه
    motivation = models.TextField('دلایل و انگیزه', blank=True)

    # پیگیری
    tracking_code = models.CharField('کد پیگیری', max_length=10, unique=True, db_index=True)

    # وضعیت
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    # پردازش کارشناس
    assigned_to      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_agency_apps', verbose_name='مسئول بررسی')
    reviewed_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_agency_apps', verbose_name='بررسی‌کننده')
    staff_note       = models.TextField('یادداشت داخلی', blank=True)
    rejection_reason = models.TextField('دلیل رد', blank=True)
    info_request_note = models.TextField('توضیح درخواست اطلاعات', blank=True)

    # کاربر ایجادشده پس از تأیید
    created_user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='from_agency_application', verbose_name='کاربر ایجادشده')

    # زمان‌ها
    created_at   = models.DateTimeField('تاریخ ثبت', auto_now_add=True)
    submitted_at = models.DateTimeField('تاریخ ارسال', null=True, blank=True)
    reviewed_at  = models.DateTimeField('تاریخ بررسی', null=True, blank=True)
    updated_at   = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'درخواست نمایندگی'
        verbose_name_plural = 'درخواست‌های نمایندگی'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.first_name} {self.last_name} — {self.phone} — {self.get_status_display()}'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def status_class(self):
        return self.STATUS_CLASS.get(self.status, 'flag-gray')

    @property
    def is_active(self):
        return self.status not in {self.STATUS_APPROVED, self.STATUS_REJECTED}


class AgencyApplicationLog(models.Model):
    ACTION_SUBMITTED   = 'submitted'
    ACTION_REVIEWING   = 'reviewing'
    ACTION_INFO_NEEDED = 'info_needed'
    ACTION_APPROVED    = 'approved'
    ACTION_REJECTED    = 'rejected'
    ACTION_NOTE        = 'note'
    ACTION_ASSIGNED    = 'assigned'

    ACTION_CHOICES = [
        (ACTION_SUBMITTED,   'ارسال درخواست'),
        (ACTION_REVIEWING,   'شروع بررسی'),
        (ACTION_INFO_NEEDED, 'درخواست اطلاعات تکمیلی'),
        (ACTION_APPROVED,    'تأیید'),
        (ACTION_REJECTED,    'رد'),
        (ACTION_NOTE,        'یادداشت'),
        (ACTION_ASSIGNED,    'تخصیص'),
    ]

    application = models.ForeignKey(AgencyApplication, on_delete=models.CASCADE, related_name='logs')
    actor       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='کاربر')
    action      = models.CharField('عملیات', max_length=20, choices=ACTION_CHOICES)
    note        = models.TextField('یادداشت', blank=True)
    created_at  = models.DateTimeField('زمان', auto_now_add=True)

    class Meta:
        verbose_name = 'لاگ درخواست نمایندگی'
        verbose_name_plural = 'لاگ‌های درخواست نمایندگی'


# ─────────────────────────────────────────────────────────────────────────────
#  گارانتی و خدمات پس از فروش
# ─────────────────────────────────────────────────────────────────────────────

def warranty_claim_file_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'warranty', 'warrantyclaimfile')


class WarrantyClaim(models.Model):
    STATUS_SUBMITTED   = 'submitted'
    STATUS_REVIEWING   = 'reviewing'
    STATUS_INFO_NEEDED = 'info_needed'
    STATUS_APPROVED    = 'approved'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED    = 'resolved'
    STATUS_REJECTED    = 'rejected'
    STATUS_CLOSED      = 'closed'

    STATUS_CHOICES = [
        (STATUS_SUBMITTED,   'ثبت شده'),
        (STATUS_REVIEWING,   'در حال بررسی'),
        (STATUS_INFO_NEEDED, 'نیاز به اطلاعات تکمیلی'),
        (STATUS_APPROVED,    'تأیید گارانتی'),
        (STATUS_IN_PROGRESS, 'در حال پردازش'),
        (STATUS_RESOLVED,    'رفع شد'),
        (STATUS_REJECTED,    'رد شده'),
        (STATUS_CLOSED,      'بسته شده'),
    ]

    STATUS_CLASS = {
        STATUS_SUBMITTED:   'flag-gray',
        STATUS_REVIEWING:   'flag-blue',
        STATUS_INFO_NEEDED: 'flag-yellow',
        STATUS_APPROVED:    'flag-green',
        STATUS_IN_PROGRESS: 'flag-blue',
        STATUS_RESOLVED:    'flag-green',
        STATUS_REJECTED:    'flag-red',
        STATUS_CLOSED:      'flag-gray',
    }

    PRIORITY_LOW    = 'low'
    PRIORITY_NORMAL = 'normal'
    PRIORITY_HIGH   = 'high'
    PRIORITY_URGENT = 'urgent'

    PRIORITY_CHOICES = [
        (PRIORITY_LOW,    'کم'),
        (PRIORITY_NORMAL, 'معمولی'),
        (PRIORITY_HIGH,   'زیاد'),
        (PRIORITY_URGENT, 'فوری'),
    ]

    RESOLUTION_REPAIR   = 'repair'
    RESOLUTION_REPLACE  = 'replace'
    RESOLUTION_REFUND   = 'refund'

    RESOLUTION_CHOICES = [
        (RESOLUTION_REPAIR,  'تعمیر'),
        (RESOLUTION_REPLACE, 'تعویض'),
        (RESOLUTION_REFUND,  'استرداد وجه'),
    ]

    # مشتری / متقاضی
    user           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='warranty_claims', verbose_name='کاربر (مشتری)')
    submitted_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='submitted_warranty_claims', verbose_name='ثبت‌کننده')
    claimant_name  = models.CharField('نام متقاضی', max_length=100)
    claimant_phone = models.CharField('موبایل متقاضی', max_length=20)
    claimant_email = models.EmailField('ایمیل', blank=True)

    # قطعه / محصول
    part_name      = models.CharField('نام قطعه / محصول', max_length=200)
    part_model     = models.CharField('مدل / شناسه', max_length=200, blank=True)
    serial_number  = models.CharField('شماره سریال', max_length=100, db_index=True)
    purchase_date  = models.DateField('تاریخ خرید')
    invoice_number = models.CharField('شماره فاکتور', max_length=100, blank=True)

    # شرح خرابی
    defect_description = models.TextField('شرح خرابی')
    customer_reply     = models.TextField('توضیح تکمیلی مشتری', blank=True)

    # ردیابی
    tracking_code = models.CharField('کد پیگیری', max_length=12, unique=True, db_index=True)
    status        = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES,
                                     default=STATUS_SUBMITTED, db_index=True)
    priority      = models.CharField('اولویت', max_length=10, choices=PRIORITY_CHOICES,
                                     default=PRIORITY_NORMAL, db_index=True)

    # کارشناس گارانتی
    assigned_to       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='assigned_warranty_claims', verbose_name='مسئول بررسی')
    resolution_type   = models.CharField('نوع رفع مسئله', max_length=20, choices=RESOLUTION_CHOICES, blank=True)
    resolution_note   = models.TextField('توضیح رفع مسئله', blank=True)
    staff_note        = models.TextField('یادداشت داخلی', blank=True)
    info_request_note = models.TextField('توضیح درخواست اطلاعات', blank=True)
    rejection_reason  = models.TextField('دلیل رد', blank=True)

    # زمان / SLA
    created_at  = models.DateTimeField('تاریخ ثبت', auto_now_add=True)
    updated_at  = models.DateTimeField('آخرین بروزرسانی', auto_now=True)
    reviewed_at = models.DateTimeField('تاریخ شروع بررسی', null=True, blank=True)
    resolved_at = models.DateTimeField('تاریخ رفع', null=True, blank=True)
    due_date    = models.DateTimeField('موعد پاسخ SLA', null=True, blank=True)

    # رضایت‌سنجی
    customer_rating   = models.PositiveSmallIntegerField('امتیاز مشتری', null=True, blank=True)
    customer_feedback = models.TextField('بازخورد مشتری', blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'درخواست گارانتی'
        verbose_name_plural = 'درخواست‌های گارانتی'

    def __str__(self):
        return f'گارانتی #{self.id} — {self.part_name}'

    @property
    def status_class(self):
        return self.STATUS_CLASS.get(self.status, 'flag-gray')

    @property
    def priority_class(self):
        return {
            self.PRIORITY_LOW:    'flag-gray',
            self.PRIORITY_NORMAL: 'flag-blue',
            self.PRIORITY_HIGH:   'flag-orange',
            self.PRIORITY_URGENT: 'flag-red',
        }.get(self.priority, 'flag-gray')

    @property
    def is_open(self):
        return self.status not in {self.STATUS_RESOLVED, self.STATUS_REJECTED, self.STATUS_CLOSED}

    @property
    def is_overdue(self):
        return bool(self.due_date and timezone.now() > self.due_date and self.is_open)


class WarrantyClaimFile(models.Model):
    claim       = models.ForeignKey(WarrantyClaim, on_delete=models.CASCADE, related_name='files')
    file        = models.FileField('فایل', upload_to=warranty_claim_file_upload_to)
    description = models.CharField('توضیح', max_length=200, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='warranty_claim_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        verbose_name = 'فایل گارانتی'
        verbose_name_plural = 'فایل‌های گارانتی'


class WarrantyClaimLog(models.Model):
    ACTION_SUBMITTED      = 'submitted'
    ACTION_REVIEWING      = 'reviewing'
    ACTION_INFO_NEEDED    = 'info_needed'
    ACTION_CUSTOMER_REPLY = 'customer_reply'
    ACTION_APPROVED       = 'approved'
    ACTION_IN_PROGRESS    = 'in_progress'
    ACTION_RESOLVED       = 'resolved'
    ACTION_REJECTED       = 'rejected'
    ACTION_CLOSED         = 'closed'
    ACTION_NOTE           = 'note'
    ACTION_ASSIGNED       = 'assigned'
    ACTION_PRIORITY       = 'priority'
    ACTION_FILE           = 'file'
    ACTION_RATED          = 'rated'

    ACTION_CHOICES = [
        (ACTION_SUBMITTED,      'ثبت درخواست'),
        (ACTION_REVIEWING,      'شروع بررسی'),
        (ACTION_INFO_NEEDED,    'درخواست اطلاعات تکمیلی'),
        (ACTION_CUSTOMER_REPLY, 'پاسخ مشتری'),
        (ACTION_APPROVED,       'تأیید گارانتی'),
        (ACTION_IN_PROGRESS,    'شروع پردازش'),
        (ACTION_RESOLVED,       'رفع شد'),
        (ACTION_REJECTED,       'رد گارانتی'),
        (ACTION_CLOSED,         'بسته شدن'),
        (ACTION_NOTE,           'یادداشت'),
        (ACTION_ASSIGNED,       'تخصیص'),
        (ACTION_PRIORITY,       'تغییر اولویت'),
        (ACTION_FILE,           'بارگذاری فایل'),
        (ACTION_RATED,          'ثبت امتیاز'),
    ]

    claim                  = models.ForeignKey(WarrantyClaim, on_delete=models.CASCADE, related_name='logs')
    actor                  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action                 = models.CharField('اقدام', max_length=30, choices=ACTION_CHOICES)
    note                   = models.TextField('یادداشت', blank=True)
    is_visible_to_customer = models.BooleanField('قابل مشاهده توسط مشتری', default=True)
    created_at             = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'لاگ گارانتی'
        verbose_name_plural = 'لاگ‌های گارانتی'
        ordering = ['created_at']
