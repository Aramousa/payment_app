from django.core.management.base import BaseCommand

from payments.invoice_extraction import process_invoice_extraction_job
from payments.models import InvoiceExtractionJob


class Command(BaseCommand):
    help = 'Process pending invoice extraction jobs from the database.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)

    def handle(self, *args, **options):
        limit = options['limit']
        jobs = InvoiceExtractionJob.objects.filter(
            status__in=[
                InvoiceExtractionJob.STATUS_PENDING,
                InvoiceExtractionJob.STATUS_FAILED,
            ],
        ).order_by('created_at', 'id')[:limit]

        count = 0
        for job in jobs:
            process_invoice_extraction_job(job.id)
            count += 1
            self.stdout.write(self.style.SUCCESS(f'Processed invoice extraction job #{job.id}'))

        if not count:
            self.stdout.write('No pending invoice extraction jobs.')
