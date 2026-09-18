"""
هسته‌ی منطق تهیه و بازگردانی نسخه پشتیبان کامل سامانه (پایگاه‌داده + فایل‌های media).

طراحی امنیتی/عملیاتی:
- خروجی نهایی همیشه با passphrase کاربر رمزنگاری می‌شود (Fernet/AES با کلید PBKDF2) —
  چون این فایل روی کامپیوتر شخصی مدیر سیستم (خارج از سرور) نگهداری می‌شود.
- بازگردانی پایگاه‌داده با pg_restore --single-transaction انجام می‌شود: یا کامل
  موفق می‌شود یا هیچ تغییری روی داده‌های موجود اعمال نمی‌شود (اتمیک).
- اعتبارسنجی ساختار/چک‌سام فایل پشتیبان قبل از فعال‌سازی قفل نگهداری انجام می‌شود
  تا یک فایل خراب یا رمز غلط، سیستم را بی‌جهت در حالت قفل نبرد.
- فایل‌های media فقط بعد از موفقیت بازگردانی پایگاه‌داده جایگزین می‌شوند و پوشه‌ی
  قبلی حذف نمی‌شود، بلکه rename می‌شود تا در صورت نیاز قابل بازیابی دستی باشد.
"""
import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import zipfile

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
from django.utils import timezone

MANIFEST_VERSION = 1
BACKUP_FILE_MAGIC = b'VSBK1'
PBKDF2_ITERATIONS = 390_000
SUBPROCESS_TIMEOUT_SECONDS = 3600


class BackupError(Exception):
    """خطای قابل‌نمایش به کاربر — نه یک باگ برنامه."""


def _resolve_binary(name, configured_path):
    if configured_path and os.path.exists(configured_path):
        return configured_path
    found = shutil.which(name)
    if found:
        return found
    found_exe = shutil.which(name + '.exe')
    if found_exe:
        return found_exe
    raise BackupError(
        f'ابزار «{name}» روی سرور پیدا نشد. باید بسته postgresql-client (سازگار با نسخه‌ی '
        f'پایگاه‌داده سرور) نصب و در PATH باشد؛ یا مسیر کامل آن را در تنظیمات سرور مشخص کنید.'
    )


def _pg_dump_path():
    return _resolve_binary('pg_dump', settings.PG_DUMP_PATH)


def _pg_restore_path():
    return _resolve_binary('pg_restore', settings.PG_RESTORE_PATH)


def _db_settings():
    return settings.DATABASES['default']


def _db_env():
    db = _db_settings()
    env = os.environ.copy()
    env['PGPASSWORD'] = db.get('PASSWORD') or ''
    sslmode = (db.get('OPTIONS') or {}).get('sslmode')
    if sslmode:
        env['PGSSLMODE'] = sslmode
    return env


def _db_conn_args():
    db = _db_settings()
    return [
        '-h', db.get('HOST') or '127.0.0.1',
        '-p', str(db.get('PORT') or '5432'),
        '-U', db.get('USER') or '',
        '-d', db.get('NAME') or '',
    ]


def _sha256_of_file(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            h.update(chunk)
    return h.hexdigest()


def _derive_key(passphrase, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))


# ---------------------------------------------------------------------------
# تهیه نسخه پشتیبان
# ---------------------------------------------------------------------------

def create_backup_zip(dest_path):
    """پایگاه‌داده (pg_dump -Fc) + تمام فایل‌های MEDIA_ROOT را در dest_path (zip) می‌سازد."""
    pg_dump = _pg_dump_path()
    tmp_dump_path = dest_path + '.dump.tmp'
    try:
        cmd = [pg_dump, *_db_conn_args(), '-Fc', '-f', tmp_dump_path]
        result = subprocess.run(
            cmd, env=_db_env(), capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise BackupError(f'خطا در تهیه نسخه پشتیبان پایگاه‌داده:\n{result.stderr[-4000:]}')

        db_sha256 = _sha256_of_file(tmp_dump_path)
        media_root = str(settings.MEDIA_ROOT)
        file_count = 0
        total_media_size = 0

        with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_dump_path, arcname='database.dump')
            if os.path.isdir(media_root):
                for root, _dirs, files in os.walk(media_root):
                    for fname in files:
                        full_path = os.path.join(root, fname)
                        rel_path = os.path.relpath(full_path, media_root)
                        arcname = 'media/' + rel_path.replace(os.sep, '/')
                        try:
                            zf.write(full_path, arcname=arcname)
                        except OSError:
                            continue
                        file_count += 1
                        total_media_size += os.path.getsize(full_path)

            manifest = {
                'version': MANIFEST_VERSION,
                'created_at': timezone.now().isoformat(),
                'db_name': _db_settings().get('NAME'),
                'db_dump_sha256': db_sha256,
                'media_file_count': file_count,
                'media_total_size': total_media_size,
            }
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        if os.path.exists(tmp_dump_path):
            os.remove(tmp_dump_path)

    return dest_path


def encrypt_file(src_path, dest_path, passphrase):
    """فایل src_path را با passphrase رمزنگاری می‌کند و در dest_path می‌نویسد."""
    salt = secrets.token_bytes(16)
    key = _derive_key(passphrase, salt)
    fernet = Fernet(key)
    with open(src_path, 'rb') as f:
        data = f.read()
    token = fernet.encrypt(data)
    with open(dest_path, 'wb') as out:
        out.write(BACKUP_FILE_MAGIC)
        out.write(salt)
        out.write(token)


def decrypt_file(src_path, dest_path, passphrase):
    """عکس encrypt_file — در صورت رمز غلط یا فایل خراب، BackupError می‌دهد."""
    with open(src_path, 'rb') as f:
        header = f.read(len(BACKUP_FILE_MAGIC))
        if header != BACKUP_FILE_MAGIC:
            raise BackupError('فایل انتخاب‌شده یک فایل پشتیبان معتبر این سامانه نیست.')
        salt = f.read(16)
        token = f.read()
    key = _derive_key(passphrase, salt)
    fernet = Fernet(key)
    try:
        data = fernet.decrypt(token)
    except InvalidToken:
        raise BackupError('رمز عبور فایل پشتیبان اشتباه است یا فایل خراب/دستکاری شده است.')
    with open(dest_path, 'wb') as out:
        out.write(data)


# ---------------------------------------------------------------------------
# بازگردانی نسخه پشتیبان
# ---------------------------------------------------------------------------

def validate_backup_zip(zip_path):
    """
    ساختار و چک‌سام فایل zip را بدون هیچ تغییری روی پایگاه‌داده بررسی می‌کند.
    عمداً قبل از فعال‌سازی قفل نگهداری فراخوانی می‌شود.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            if 'manifest.json' not in names or 'database.dump' not in names:
                raise BackupError('ساختار فایل پشتیبان نامعتبر است (manifest.json یا database.dump یافت نشد).')
            try:
                manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                raise BackupError('فایل manifest.json داخل نسخه پشتیبان قابل خواندن نیست.')

            bad_crc = zf.testzip()
            if bad_crc:
                raise BackupError(f'فایل «{bad_crc}» داخل نسخه پشتیبان خراب است (خطای CRC).')
    except zipfile.BadZipFile:
        raise BackupError('فایل انتخاب‌شده یک بایگانی zip معتبر نیست (احتمالاً رمز عبور اشتباه است).')

    return manifest


def apply_restore(zip_path):
    """
    فقط باید وقتی فراخوانی شود که قفل نگهداری فعال است.
    ۱. pg_restore --single-transaction روی پایگاه‌داده (اتمیک — یا کامل یا هیچ)
    ۲. فقط در صورت موفقیت مرحله ۱، فایل‌های media جایگزین می‌شوند
    """
    pg_restore = _pg_restore_path()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))

        dump_dest = zip_path + '.database.dump'
        with zf.open('database.dump') as src, open(dump_dest, 'wb') as dst:
            shutil.copyfileobj(src, dst)

        expected_sha = manifest.get('db_dump_sha256')
        if expected_sha:
            actual_sha = _sha256_of_file(dump_dest)
            if actual_sha != expected_sha:
                os.remove(dump_dest)
                raise BackupError(
                    'چک‌سام database.dump با مقدار ثبت‌شده در manifest.json مطابقت ندارد؛ '
                    'فایل ممکن است خراب یا ناقص باشد. بازگردانی متوقف شد و هیچ تغییری اعمال نشد.'
                )

        try:
            cmd = [
                pg_restore, *_db_conn_args(),
                '--clean', '--if-exists', '--no-owner', '--no-privileges',
                '--single-transaction',
                dump_dest,
            ]
            result = subprocess.run(
                cmd, env=_db_env(), capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        finally:
            if os.path.exists(dump_dest):
                os.remove(dump_dest)

        if result.returncode != 0:
            raise BackupError(
                'بازگردانی پایگاه‌داده ناموفق بود. چون از یک تراکنش یکپارچه (single-transaction) '
                'استفاده شده، هیچ تغییری روی داده‌های فعلی اعمال نشده است:\n'
                f'{result.stderr[-4000:]}'
            )

        # ---- از این نقطه به بعد، پایگاه‌داده با موفقیت بازگردانی شده ----
        media_root = str(settings.MEDIA_ROOT)
        media_names = [n for n in names if n.startswith('media/') and not n.endswith('/')]
        if media_names:
            if os.path.isdir(media_root):
                backup_old_dir = f'{media_root}__pre_restore_{timezone.now().strftime("%Y%m%d_%H%M%S")}'
                os.rename(media_root, backup_old_dir)
            os.makedirs(media_root, exist_ok=True)
            for name in media_names:
                rel = name[len('media/'):]
                target_path = os.path.join(media_root, *rel.split('/'))
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(name) as src, open(target_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

    return manifest
