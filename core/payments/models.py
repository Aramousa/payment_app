from django.db import models
from django.contrib.auth.models import User
from django_jalali.db import models as jmodels

class PaymentRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'در انتظار بررسی'),
        ('approved', 'تأیید شده'),
        ('rejected', 'رد شده'),
        ('archived', 'بایگانی شده'),
    ]

#    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    organization = models.CharField(max_length=100)
    city = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    amount = models.BigIntegerField() 
    pay_date = jmodels.jDateField(verbose_name='تاریخ واریز')
    tracking_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='کد پیگیری'
    )
    receipt_image = models.ImageField(upload_to='receipts/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.amount}"
class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('customer', 'مشتری'),
        ('staff', 'کارمند'),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    phone = models.CharField('شماره تلفن', max_length=20)
    organization = models.CharField('نام مجموعه', max_length=100, blank=True)
    city = models.CharField('شهر', max_length=50, blank=True)
    role = models.CharField(
        'نوع کاربر',
        max_length=10,
        choices=ROLE_CHOICES,
        default='customer'
    )

    def __str__(self):
        return self.user.username