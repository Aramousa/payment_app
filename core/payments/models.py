import uuid
import os

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django_jalali.db import models as jmodels


def _safe_upload_extension(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    safe_ext = ''.join(ch for ch in ext if ch in '.abcdefghijklmnopqrstuvwxyz0123456789')
    if safe_ext == '.' or len(safe_ext) > 16:
        return ''
    return safe_ext


def _upload_actor_id(instance):
    for attr in ('user', 'customer', 'uploaded_by', 'issued_by', 'requested_by'):
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


def invoice_extraction_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'invoice_extractions', 'invoiceextractionjob')


def price_list_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'price_lists', 'pricelist')


def proforma_upload_to(instance, filename):
    return _unique_upload_path(instance, filename, 'proformas', 'proformainvoice')


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
    STATUS_FINANCE_REVIEW = 'finance_review'
    STATUS_APPROVED = 'approved'
    STATUS_FINAL_APPROVED = 'final_approved'
    STATUS_REJECTED = 'rejected'
    STATUS_INCOMPLETE = 'incomplete'
    STATUS_RETURNED_TO_COMMERCIAL = 'returned_commercial'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'در حال بررسی'),
        (STATUS_COMMERCIAL_REVIEW, 'بررسی بازرگانی'),
        (STATUS_FINANCE_REVIEW, 'ثبت مالی'),
        (STATUS_APPROVED, 'ثبت بازرگانی'),
        (STATUS_FINAL_APPROVED, 'تایید نهایی'),
        (STATUS_REJECTED, 'رد شده'),
        (STATUS_INCOMPLETE, 'ناقص'),
        (STATUS_RETURNED_TO_COMMERCIAL, 'عودت به بازرگانی'),
    ]

    CUSTOMER_VISIBLE_LABELS = {
        STATUS_PENDING: 'در حال بررسی',
        STATUS_COMMERCIAL_REVIEW: 'در حال بررسی',
        STATUS_FINANCE_REVIEW: 'در حال بررسی',
        STATUS_RETURNED_TO_COMMERCIAL: 'در حال بررسی',
        STATUS_APPROVED: 'ثبت بازرگانی',
        STATUS_FINAL_APPROVED: 'تایید نهایی',
        STATUS_REJECTED: 'رد شده',
        STATUS_INCOMPLETE: 'ناقص',
    }

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
    locked_by_finance = models.BooleanField(default=False)
    last_staff_note = models.TextField('آخرین توضیح کارشناس', blank=True)
    customer_notes = models.TextField('توضیحات مشتری', blank=True, help_text='توضیحات یا نکات مشتری در مورد این واریزی')
    created_at = models.DateTimeField(auto_now_add=True)
    customer_seen_at = models.DateTimeField('زمان مشاهده مشتری', null=True, blank=True)

    # تایید طرف حساب
    counterparty_approved_at = models.DateTimeField('زمان تایید طرف حساب', null=True, blank=True, db_index=True)
    counterparty_approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='counterparty_approvals',
        verbose_name='تایید شده توسط طرف حساب',
    )

    @property
    def is_counterparty_approved(self):
        return self.counterparty_approved_at is not None

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.amount}"

    @property
    def customer_status_label(self):
        return self.CUSTOMER_VISIBLE_LABELS.get(self.status, 'در حال بررسی')

    @property
    def commercial_status_label(self):
        if self.status == self.STATUS_PENDING:
            return 'در حال بررسی'
        if self.status == self.STATUS_COMMERCIAL_REVIEW:
            return 'بررسی بازرگانی'
        if self.status in {self.STATUS_APPROVED, self.STATUS_FINAL_APPROVED}:
            return 'ثبت بازرگانی'
        if self.status == self.STATUS_RETURNED_TO_COMMERCIAL:
            return 'عودت به بازرگانی'
        if self.status == self.STATUS_REJECTED:
            return 'رد شده'
        if self.status == self.STATUS_INCOMPLETE:
            return 'ناقص'
        return self.get_status_display()

    @property
    def commercial_flag_class(self):
        if self.status == self.STATUS_COMMERCIAL_REVIEW:
            return 'flag-blue'
        if self.status in {self.STATUS_APPROVED, self.STATUS_FINAL_APPROVED}:
            return 'flag-orange'
        if self.status == self.STATUS_REJECTED:
            return 'flag-red'
        if self.status == self.STATUS_INCOMPLETE:
            return 'flag-yellow'
        return 'flag-gray'

    @property
    def finance_status_label(self):
        if self.status in {self.STATUS_PENDING, self.STATUS_COMMERCIAL_REVIEW, self.STATUS_INCOMPLETE}:
            return 'در انتظار بازرگانی'
        if self.status == self.STATUS_RETURNED_TO_COMMERCIAL:
            return 'عودت به بازرگانی'
        if self.status == self.STATUS_APPROVED:
            return 'در انتظار ثبت مالی'
        if self.status == self.STATUS_FINAL_APPROVED:
            return 'تایید نهایی'
        if self.status == self.STATUS_REJECTED:
            return 'رد شده'
        return self.get_status_display()

    @property
    def finance_flag_class(self):
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
    def status_flag_class(self):
        return {
            self.STATUS_COMMERCIAL_REVIEW: 'flag-blue',
            self.STATUS_FINANCE_REVIEW: 'flag-orange',
            self.STATUS_APPROVED: 'flag-orange',
            self.STATUS_FINAL_APPROVED: 'flag-green',
            self.STATUS_REJECTED: 'flag-red',
            self.STATUS_INCOMPLETE: 'flag-yellow',
            self.STATUS_RETURNED_TO_COMMERCIAL: 'flag-gray',
        }.get(self.status, 'flag-gray')

    @property
    def customer_flag_class(self):
        if self.status == self.STATUS_FINANCE_REVIEW:
            return 'flag-orange'
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
        ('customer', 'مشتری'),
        ('finance', 'واحد مالی'),
        ('finance_manager', 'مدیر مالی'),
        ('commercial', 'واحد بازرگانی'),
        ('commercial_manager', 'مدیر بازرگانی'),
        ('sales', 'فروش'),
        ('sales_manager', 'مدیر فروش'),
        ('data_entry', 'تکمیل اطلاعات فیش'),
        ('staff', 'کارمند'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField('نام', max_length=50, blank=True)
    last_name = models.CharField('نام خانوادگی', max_length=50, blank=True)
    phone = models.CharField('شماره تلفن', max_length=20, blank=True)
    mobile = models.CharField('شماره همراه', max_length=20, blank=True)
    second_mobile = models.CharField('شماره همراه دوم', max_length=20, blank=True)
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
    accounting_code = models.CharField('کد تفضیلی', max_length=50, blank=True)

    def __str__(self):
        return self.user.username


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
            items.append({
                'field': field_name,
                'label': self.FIELD_LABELS.get(field_name, field_name),
                'old': (values or {}).get('old') or '-',
                'new': (values or {}).get('new') or '-',
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
    ACTION_CP_APPROVED          = 'cp_approved'
    ACTION_CP_RETURNED          = 'cp_returned'

    ACTION_CHOICES = [
        (ACTION_CREATED,          'ایجاد'),
        (ACTION_EDITED,           'ویرایش'),
        (ACTION_STATUS_CHANGED,   'تغییر وضعیت'),
        (ACTION_VIEWED,           'رویت'),
        (ACTION_CUSTOMER_NOTE,    'توضیح مشتری'),
        (ACTION_CP_APPROVED,      'تایید طرف حساب'),
        (ACTION_CP_RETURNED,      'بازگشت از طرف حساب'),
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
        default=30,
        help_text='پس از این مدت بی‌فعالیت، کاربر به‌صورت خودکار خارج می‌شود.',
    )
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
