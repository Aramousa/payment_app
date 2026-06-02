"""
سرویس یکپارچه ارسال پیامک
پشتیبانی از: کاوه‌نگار، قاصدک، HTTP عمومی

استفاده:
    from payments.sms_service import send_sms, send_otp
    send_sms('09123456789', 'متن پیام', purpose='notification')
    otp = send_otp(user, purpose='mfa')  # returns SMSOTPCode or None
"""

import hashlib
import logging
import random
import string
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

_settings_cache = None
_settings_cache_ts = None
_SETTINGS_TTL = 60  # seconds


def _get_sms_settings():
    """کش تنظیمات پیامک — هر ۶۰ ثانیه از DB می‌خواند."""
    global _settings_cache, _settings_cache_ts
    now = timezone.now().timestamp()
    if _settings_cache is None or (now - (_settings_cache_ts or 0)) > _SETTINGS_TTL:
        from .models import SystemSettings
        _settings_cache = SystemSettings.load()
        _settings_cache_ts = now
    return _settings_cache


def _invalidate_settings_cache():
    global _settings_cache
    _settings_cache = None


# ─── بک‌اند کاوه‌نگار ──────────────────────────────────────────────────────

def _send_kavenegar(api_key, sender, recipient, message):
    import urllib.request
    import urllib.parse
    import json

    url = f'https://api.kavenegar.com/v1/{api_key}/sms/send.json'
    data = urllib.parse.urlencode({
        'receptor': recipient,
        'sender':   sender,
        'message':  message,
    }).encode('utf-8')

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Accept', 'application/json')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode('utf-8'))

    entries = result.get('entries') or []
    if entries and entries[0].get('statustext') == 'Sent':
        return True, ''
    return False, str(result.get('return', {}).get('message', 'unknown'))


# ─── بک‌اند قاصدک ───────────────────────────────────────────────────────────

def _send_ghasedak(api_key, sender, recipient, message):
    import urllib.request
    import urllib.parse
    import json

    url = 'https://gateway.ghasedak.me/rest/api/v1/WebService/SendSMS'
    data = urllib.parse.urlencode({
        'receptor': recipient,
        'linenumber': sender,
        'message': message,
        'senddate': '',
        'checkid': '',
    }).encode('utf-8')

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('apikey', api_key)
    req.add_header('Accept', 'application/json')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode('utf-8'))

    if result.get('result', {}).get('code') == 200:
        return True, ''
    return False, str(result.get('result', {}).get('description', 'unknown'))


# ─── بک‌اند HTTP عمومی ──────────────────────────────────────────────────────

def _send_generic(api_key, sender, recipient, message, url, extra_params):
    import urllib.request
    import urllib.parse
    import json

    body = {
        'api_key':   api_key,
        'sender':    sender,
        'receptor':  recipient,
        'message':   message,
    }
    body.update(extra_params or {})

    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')

    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()

    return True, ''


# ─── تابع اصلی ارسال ────────────────────────────────────────────────────────

def send_sms(recipient, message, purpose='general'):
    """
    ارسال پیامک از طریق اپراتور تنظیم‌شده.
    Returns (success: bool, error: str)
    """
    from .models import SMSSendLog

    cfg = _get_sms_settings()
    provider = cfg.sms_provider

    if provider == 'disabled' or not cfg.sms_api_key:
        return False, 'پیامک غیرفعال است'

    recipient = _normalize_phone(recipient)
    if not recipient:
        return False, 'شماره گیرنده نامعتبر است'

    try:
        if provider == 'kavenegar':
            ok, err = _send_kavenegar(cfg.sms_api_key, cfg.sms_sender, recipient, message)
        elif provider == 'ghasedak':
            ok, err = _send_ghasedak(cfg.sms_api_key, cfg.sms_sender, recipient, message)
        elif provider == 'generic':
            ok, err = _send_generic(
                cfg.sms_api_key, cfg.sms_sender, recipient, message,
                cfg.sms_generic_url, cfg.sms_generic_extra,
            )
        else:
            return False, f'اپراتور ناشناخته: {provider}'
    except Exception as exc:
        err = str(exc)
        ok = False
        logger.exception('SMS send failed to %s via %s', recipient, provider)

    try:
        SMSSendLog.objects.create(
            recipient=recipient,
            message=message,
            purpose=purpose,
            status=SMSSendLog.STATUS_SENT if ok else SMSSendLog.STATUS_FAILED,
            provider=provider,
            error='' if ok else err,
        )
    except Exception:
        logger.exception('Failed to save SMS send log')

    if not ok:
        logger.error('SMS failed to %s: %s', recipient, err)

    return ok, err


# ─── OTP ─────────────────────────────────────────────────────────────────────

def _generate_otp_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


def _normalize_phone(phone):
    """تبدیل شماره ایرانی به فرمت استاندارد 09xxxxxxxxx."""
    p = (phone or '').strip().replace(' ', '').replace('-', '')
    if p.startswith('+98'):
        p = '0' + p[3:]
    if p.startswith('98') and len(p) == 12:
        p = '0' + p[2:]
    return p if p.startswith('0') and len(p) == 11 else p


def send_otp(user, purpose='mfa', ref_id=''):
    """
    تولید و ارسال کد OTP برای کاربر.
    Returns SMSOTPCode instance or None on failure.
    """
    from .models import SMSOTPCode

    try:
        profile = user.profile
    except Exception:
        logger.warning('send_otp: user %s has no profile', user.username)
        return None

    phone = profile.sms_number
    if not phone:
        logger.warning('send_otp: user %s has no phone number', user.username)
        return None

    cfg = _get_sms_settings()
    expiry_minutes = cfg.sms_otp_expiry_minutes or 5
    code = _generate_otp_code()

    otp = SMSOTPCode.objects.create(
        user=user,
        phone=phone,
        code=_hash_code(code),
        purpose=purpose,
        ref_id=ref_id or '',
        expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
    )

    message = cfg.sms_otp_template.format(code=code, minutes=expiry_minutes)
    ok, err = send_sms(phone, message, purpose=f'otp_{purpose}')

    if not ok:
        otp.delete()
        return None

    # کد اصلی (hash نشده) را فقط در این لحظه برمی‌گردانیم
    otp._plain_code = code
    return otp


def _hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


def verify_otp(user, submitted_code, purpose='mfa', ref_id=''):
    """
    بررسی کد OTP ارسال‌شده توسط کاربر.
    Returns (ok: bool, message: str)
    """
    from .models import SMSOTPCode

    otps = SMSOTPCode.objects.filter(
        user=user,
        purpose=purpose,
        is_used=False,
    ).order_by('-created_at')

    if ref_id:
        otps = otps.filter(ref_id=ref_id)

    otp = otps.first()

    if not otp:
        return False, 'کد معتبری یافت نشد.'

    if otp.is_expired:
        return False, 'کد منقضی شده است. لطفاً کد جدید درخواست کنید.'

    otp.attempts += 1
    if otp.attempts >= 5:
        otp.is_used = True
        otp.save(update_fields=['attempts', 'is_used'])
        return False, 'تعداد تلاش‌های مجاز پایان یافت. کد جدید درخواست کنید.'

    if otp.code != _hash_code(submitted_code.strip()):
        otp.save(update_fields=['attempts'])
        remaining = 5 - otp.attempts
        return False, f'کد وارد شده اشتباه است. {remaining} تلاش باقی‌مانده.'

    otp.is_used = True
    otp.save(update_fields=['is_used', 'attempts'])
    return True, 'تأیید شد.'


# ─── ارسال اطلاع‌رسانی پیامکی ────────────────────────────────────────────────

def notify_sms(user, message, purpose='notification'):
    """
    ارسال پیامک اطلاع‌رسانی به کاربر (اگر پیامک فعال باشد).
    سایلنت — خطاها لاگ می‌شوند ولی exception نمی‌اندازد.
    """
    cfg = _get_sms_settings()
    if not cfg.sms_notifications_enabled:
        return

    try:
        phone = user.profile.sms_number
    except Exception:
        return

    if not phone:
        return

    send_sms(phone, message, purpose=purpose)
