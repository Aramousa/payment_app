from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0098_void_workflow'),
    ]

    operations = [
        # حذف void_pending از choices وضعیت — جایگزین با returned_finance + is_void_return
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
                    ('follow_up',           'پیگیری'),
                    ('void_confirmed',      'باطل شده'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        # فلگ تشخیص عودت برای ابطال
        migrations.AddField(
            model_name='paymentrecord',
            name='is_void_return',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='اگر True باشد، این عودت به مالی برای ابطال سند است نه بررسی مجدد.',
                verbose_name='عودت برای ابطال',
            ),
        ),
        # افزودن action برگشت ثبت مالی به choices لاگ
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
                ],
                max_length=20,
            ),
        ),
    ]
