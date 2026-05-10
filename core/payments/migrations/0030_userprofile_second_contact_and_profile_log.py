from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0029_alter_invoicerecord_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='شماره تلفن'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='second_address',
            field=models.TextField(blank=True, verbose_name='آدرس دوم'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='second_mobile',
            field=models.CharField(blank=True, max_length=20, verbose_name='شماره همراه دوم'),
        ),
        migrations.AlterField(
            model_name='systemactivitylog',
            name='action',
            field=models.CharField(
                choices=[
                    ('user_created', 'ایجاد کاربر'),
                    ('user_updated', 'ویرایش کاربر'),
                    ('password_reset', 'ریست رمز عبور'),
                    ('profile_updated', 'ویرایش مشخصات کاربر'),
                ],
                max_length=40,
                verbose_name='عملیات',
            ),
        ),
    ]
