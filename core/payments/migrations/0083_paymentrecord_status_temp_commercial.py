from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0082_systemsettings_accounting_code_import_enabled'),
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
                ],
                default='pending',
                max_length=30,
                verbose_name='وضعیت',
            ),
        ),
    ]
