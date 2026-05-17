from pathlib import Path

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Checks whether runtime storage paths are writable by the running Django user.'

    def handle(self, *args, **options):
        failures = []

        db_name = settings.DATABASES['default'].get('NAME')
        if db_name:
            db_path = Path(db_name)
            db_parent = db_path.parent
            if not db_parent.exists():
                failures.append(f'Database directory does not exist: {db_parent}')
            else:
                self.stdout.write(f'Database path: {db_path}')

        try:
            session = Session.objects.create(
                session_key='runtime_storage_check',
                session_data='',
                expire_date=timezone.now(),
            )
            session.delete()
            self.stdout.write(self.style.SUCCESS('Database/session write check: OK'))
        except Exception as exc:
            failures.append(f'Database/session write check failed: {exc}')

        media_root = Path(settings.MEDIA_ROOT)
        try:
            media_root.mkdir(parents=True, exist_ok=True)
            probe = media_root / '.runtime-write-check'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink()
            self.stdout.write(self.style.SUCCESS('Media write check: OK'))
        except Exception as exc:
            failures.append(f'Media write check failed: {exc}')

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(failure))
            raise CommandError('Runtime storage is not writable. Fix server file ownership/permissions and run migrate.')

        self.stdout.write(self.style.SUCCESS('Runtime storage checks passed.'))
