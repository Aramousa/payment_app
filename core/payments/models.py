from django.core.exceptions import ValidationError
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
        raise ValidationError('Counterparty records are permanent and cannot be deleted.')


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
        (STATUS_APPROVED, 'تایید شده'),
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
        STATUS_APPROVED: 'تایید نهایی',
        STATUS_FINAL_APPROVED: 'تایید نهایی',
        STATUS_REJECTED: 'رد شده',
        STATUS_INCOMPLETE: 'ناقص',
    }

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    counterparty = models.ForeignKey(Counterparty, on_delete=models.PROTECT, null=True, blank=True, related_name='payments')
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    organization = models.CharField(max_length=100)
    city = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    amount = models.BigIntegerField()
    pay_date = jmodels.jDateField(verbose_name='تاریخ واریز')
    tracking_code = models.CharField(max_length=50, blank=True, null=True, verbose_name='کد پیگیری')
    payer_account_number = models.CharField(max_length=64, blank=True, default='')
    payer_full_name = models.CharField(max_length=128, blank=True, default='')
    payer_bank_name = models.CharField(max_length=64, blank=True, default='')
    receipt_image = models.ImageField(upload_to='receipts/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    locked_by_finance = models.BooleanField(default=False)
    last_staff_note = models.TextField('آخرین توضیح کارشناس', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.amount}"

    @property
    def customer_status_label(self):
        return self.CUSTOMER_VISIBLE_LABELS.get(self.status, 'در حال بررسی')

    @property
    def status_flag_class(self):
        return {
            self.STATUS_COMMERCIAL_REVIEW: 'flag-blue',
            self.STATUS_FINANCE_REVIEW: 'flag-purple',
            self.STATUS_APPROVED: 'flag-green',
            self.STATUS_FINAL_APPROVED: 'flag-green',
            self.STATUS_REJECTED: 'flag-red',
            self.STATUS_INCOMPLETE: 'flag-yellow',
            self.STATUS_RETURNED_TO_COMMERCIAL: 'flag-blue',
        }.get(self.status, 'flag-gray')

    @property
    def customer_flag_class(self):
        if self.status == self.STATUS_FINANCE_REVIEW:
            return 'flag-purple'
        if self.status in {self.STATUS_PENDING, self.STATUS_COMMERCIAL_REVIEW, self.STATUS_RETURNED_TO_COMMERCIAL}:
            return 'flag-blue'
        if self.status in {self.STATUS_APPROVED, self.STATUS_FINAL_APPROVED}:
            return 'flag-green'
        if self.status == self.STATUS_REJECTED:
            return 'flag-red'
        if self.status == self.STATUS_INCOMPLETE:
            return 'flag-yellow'
        return 'flag-gray'


class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('customer', 'مشتری'),
        ('finance', 'واحد مالی'),
        ('commercial', 'واحد بازرگانی'),
        ('staff', 'کارمند'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField('شماره تلفن', max_length=20)
    organization = models.CharField('نام مجموعه', max_length=100, blank=True)
    city = models.CharField('شهر', max_length=50, blank=True)
    role = models.CharField('نوع کاربر', max_length=10, choices=ROLE_CHOICES, default='customer')

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
