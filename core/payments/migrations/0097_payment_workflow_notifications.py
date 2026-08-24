from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0096_daily_payment_assignment_sales_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'در حال بررسی'),
                    ('commercial_review', 'بررسی بازرگانی'),
                    ('temp_commercial', 'ثبت موقت بازرگانی'),
                    ('approved', 'ثبت بازرگانی'),
                    ('final_approved', 'تایید نهایی'),
                    ('rejected', 'رد شده'),
                    ('incomplete', 'ناقص'),
                    ('returned_commercial', 'عودت به بازرگانی'),
                    ('returned_finance', 'عودت به مالی'),
                    ('follow_up', 'پیگیری'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='usernotification',
            name='color',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='رنگ اعلان'),
        ),
    ]
