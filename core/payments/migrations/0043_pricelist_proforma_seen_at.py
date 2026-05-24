from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0042_pricelist_batch_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelist',
            name='customer_seen_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='زمان مشاهده مشتری'),
        ),
        migrations.AddField(
            model_name='proformainvoice',
            name='customer_seen_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='زمان مشاهده مشتری'),
        ),
    ]
