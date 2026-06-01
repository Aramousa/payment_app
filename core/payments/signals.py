from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import LoginRecord, UserProfile, UserSession


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def enforce_single_session(sender, request, user, **kwargs):
    new_key = request.session.session_key
    if not new_key:
        return

    # خروج خودکار session قبلی
    existing = UserSession.objects.filter(user=user).first()
    if existing and existing.session_key != new_key:
        Session.objects.filter(session_key=existing.session_key).delete()
        existing.session_key = new_key
        existing.save(update_fields=['session_key', 'updated_at'])
    else:
        UserSession.objects.update_or_create(
            user=user,
            defaults={'session_key': new_key},
        )

    # ثبت سابقه ورود
    try:
        _create_login_record(request, user, new_key)
    except Exception:
        pass


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    if not user:
        return
    session_key = getattr(request.session, 'session_key', None) or ''
    try:
        LoginRecord.objects.filter(
            user=user,
            session_key=session_key,
            logout_at__isnull=True,
        ).update(logout_at=timezone.now(), logout_reason=LoginRecord.LOGOUT_MANUAL)
    except Exception:
        pass


def _create_login_record(request, user, session_key):
    from user_agents import parse as ua_parse

    ua_string = request.META.get('HTTP_USER_AGENT', '')
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or None

    browser_family = browser_version = os_family = os_version = ''
    device_type = LoginRecord.DEVICE_DESKTOP
    device_brand = device_model = ''

    if ua_string:
        ua = ua_parse(ua_string)
        browser_family = ua.browser.family or ''
        browser_version = ua.browser.version_string or ''
        os_family = ua.os.family or ''
        os_version = ua.os.version_string or ''
        device_brand = ua.device.brand or ''
        device_model = ua.device.model or ''
        if ua.is_bot:
            device_type = LoginRecord.DEVICE_BOT
        elif ua.is_mobile:
            device_type = LoginRecord.DEVICE_MOBILE
        elif ua.is_tablet:
            device_type = LoginRecord.DEVICE_TABLET
        else:
            device_type = LoginRecord.DEVICE_DESKTOP

    LoginRecord.objects.create(
        user=user,
        session_key=session_key,
        ip_address=ip,
        x_forwarded_for=xff,
        user_agent_raw=ua_string[:1000],
        browser_family=browser_family[:100],
        browser_version=browser_version[:50],
        os_family=os_family[:100],
        os_version=os_version[:50],
        device_type=device_type,
        device_brand=device_brand[:100],
        device_model=device_model[:100],
        accept_language=request.META.get('HTTP_ACCEPT_LANGUAGE', '')[:200],
    )
