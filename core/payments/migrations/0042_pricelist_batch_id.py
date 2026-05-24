import uuid

from django.db import migrations, models


def assign_existing_batches(apps, schema_editor):
    PriceList = apps.get_model('payments', 'PriceList')
    for price_list in PriceList.objects.all().only('id', 'batch_id'):
        price_list.batch_id = uuid.uuid4()
        price_list.save(update_fields=['batch_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0041_remove_invoiceextractionjob_queue_job_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelist',
            name='batch_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, verbose_name='شناسه بسته ارسال'),
        ),
        migrations.RunPython(assign_existing_batches, migrations.RunPython.noop),
    ]
