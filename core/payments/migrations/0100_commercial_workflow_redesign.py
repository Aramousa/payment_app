import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0099_void_refactor'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # حذف follow_up از choices وضعیت بازرگانی
        migrations.AlterField(
            model_name='paymentrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending',             'در حال بررسی'),
                    ('commercial_review',   'بررسی بازرگانی'),
                    ('temp_commercial',     'ثبت موقت بازرگانی'),
                    ('approved',            'ثبت بازرگانی'),
                    ('final_approved',      'تایید نهایی'),
                    ('rejected',            'رد شده'),
                    ('incomplete',          'ناقص'),
                    ('returned_commercial', 'عودت به بازرگانی'),
                    ('returned_finance',    'عودت به مالی'),
                    ('void_confirmed',      'باطل شده'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        # فیلد needs_admin_review
        migrations.AddField(
            model_name='paymentrecord',
            name='needs_admin_review',
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name='نیاز به بررسی مدیر',
            ),
        ),
        # فیلد is_admin_edited
        migrations.AddField(
            model_name='paymentrecord',
            name='is_admin_edited',
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name='ویرایش‌شده توسط مدیر',
            ),
        ),
        # فیلد admin_edited_at
        migrations.AddField(
            model_name='paymentrecord',
            name='admin_edited_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='زمان ویرایش مدیر',
            ),
        ),
        # فیلد admin_edited_by
        migrations.AddField(
            model_name='paymentrecord',
            name='admin_edited_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='admin_edited_payments',
                to=settings.AUTH_USER_MODEL,
                verbose_name='ویرایش‌کننده (مدیر)',
            ),
        ),
        # افزودن action های مدیر به choices لاگ
        migrations.AlterField(
            model_name='paymentactivitylog',
            name='action',
            field=models.CharField(
                choices=[
                    ('created',          'ثبت سند'),
                    ('edited',           'ویرایش سند'),
                    ('status_changed',   'تغییر وضعیت بازرگانی'),
                    ('viewed',           'مشاهده'),
                    ('customer_note',    'توضیح مشتری'),
                    ('finance_reg',      'ثبت مالی'),
                    ('final_approved',   'تأیید نهایی'),
                    ('cp_approved',      'تایید طرف حساب'),
                    ('cp_returned',      'عودت/ناقص از طرف حساب'),
                    ('cp_rejected',      'رد/ابطال توسط طرف حساب'),
                    ('void_initiated',   'عودت به مالی برای ابطال'),
                    ('finance_void_rev', 'برگشت ثبت مالی'),
                    ('void_confirm',     'تأیید ابطال توسط مالی'),
                    ('admin_review_req', 'ارسال به صف بررسی مدیر'),
                    ('admin_edited',     'ویرایش توسط مدیر سیستم'),
                ],
                max_length=20,
            ),
        ),
    ]
