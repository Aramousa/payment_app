from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django_jalali.db import models as jmodels


class Counterparty(models.Model):
    name = models.CharField('طرف حساب', max_length=120, unique=True)
    description = models.CharField('توضیحات', max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        raise ValidationError('رکوردهای طرف حساب دائمی هستند و امکان حذف آن‌ها وجود ندارد.')


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
    image = models.ImageField('تصویر بنر', upload_to='login_ads/', blank=True, null=True)
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
        (STATUS_FINANCE_REVIEW, 'تایید مالی'),
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
    receipt_image = models.ImageField(upload_to='receipts/', blank=True, null=True)
    daily_assignment = models.ForeignKey('DailyPaymentAssignment', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    locked_by_finance = models.BooleanField(default=False)
    last_staff_note = models.TextField('آخرین توضیح کارشناس', blank=True)
    customer_notes = models.TextField('توضیحات مشتری', blank=True, help_text='توضیحات یا نکات مشتری در مورد این واریزی')
    created_at = models.DateTimeField(auto_now_add=True)
    customer_seen_at = models.DateTimeField('زمان مشاهده مشتری', null=True, blank=True)

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
            return 'در انتظار تایید مالی'
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
        ('commercial', 'واحد بازرگانی'),
        ('sales', 'فروش'),
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
    role = models.CharField('نوع کاربر', max_length=10, choices=ROLE_CHOICES, default='customer')
    active_from = jmodels.jDateField('تاریخ آغاز فعالیت', null=True, blank=True)
    valid_until = jmodels.jDateField('تاریخ اعتبار', null=True, blank=True)
    force_password_change = models.BooleanField('الزام تعویض رمز', default=True)
    suspended = models.BooleanField('معلق', default=False)
    can_view_invoices = models.BooleanField('دسترسی مشاهده فاکتورها', default=False)
    can_upload_invoices = models.BooleanField('دسترسی بارگذاری فاکتورها', default=False)
    can_edit_payment_details = models.BooleanField('دسترسی تکمیل اطلاعات فیش‌ها', default=False)

    def __str__(self):
        return self.user.username


class PaymentReceipt(models.Model):
    payment = models.ForeignKey(PaymentRecord, on_delete=models.CASCADE, related_name='receipts')
    image = models.FileField(upload_to='receipts/')
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
    ACTION_CREATED = 'created'
    ACTION_EDITED = 'edited'
    ACTION_STATUS_CHANGED = 'status_changed'
    ACTION_VIEWED = 'viewed'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'ایجاد'),
        (ACTION_EDITED, 'ویرایش'),
        (ACTION_STATUS_CHANGED, 'تغییر وضعیت'),
        (ACTION_VIEWED, 'رویت'),
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
    attachment = models.FileField('فایل فاکتور', upload_to='invoices/')
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
