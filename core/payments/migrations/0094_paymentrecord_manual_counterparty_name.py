from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0093_usersession_activity_ip'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentrecord',
            name='manual_counterparty_name',
            field=models.CharField(blank=True, default='', max_length=160, verbose_name='طرف حساب پیشنهادی مشتری'),
        ),
    ]
