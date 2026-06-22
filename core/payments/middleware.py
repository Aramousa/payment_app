import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

_SESSION_EXEMPT_PREFIXES = ('/accounts/', '/admin/', '/static/', '/media/', '/sms-verify/')
_SMS_OTP_VERIFY_URL = '/sms-verify/'
_COUNTERPARTY_ALLOWED_PREFIXES = ('/counterparty/', '/accounts/', '/admin/', '/static/', '/media/', '/profile/')

# کش ساده برای تنظیمات نشست — هر ۶۰ ثانیه از دیتابیس می‌خواند
_session_cache = {'timeout': None, 'allow_multi': True, 'ts': 0.0}


def _get_session_settings():
    now = time.monotonic()
    if _session_cache['timeout'] is None or now - _session_cache['ts'] > 60:
        try:
            from .models import SystemSettings
            obj = SystemSettings.load()
            _session_cache['timeout'] = obj.session_inactivity_timeout * 60
            _session_cache['allow_multi'] = obj.allow_multiple_sessions
        except Exception:
            _session_cache['timeout'] = getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', 30 * 60)
            _session_cache['allow_multi'] = True
        _session_cache['ts'] = now
    return _session_cache['timeout'], _session_cache['allow_multi']


class SingleSessionMiddleware:
    """
    ۱. ورود همزمان از چند دستگاه را ممنوع می‌کند.
    ۲. پس از مدت بی‌فعالیت (قابل تنظیم از پنل مدیریت)، کاربر را خارج می‌کند.
    ۳. دلیل خروج را در LoginRecord ثبت می‌کند.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not self._is_exempt(request):
            # طرف حساب → فقط به مسیرهای مجاز دسترسی دارد
            cp_redirect = self._check_counterparty(request)
            if cp_redirect:
                return cp_redirect

            forced = self._validate(request)
            if forced:
                return forced
        return self.get_response(request)

    def _check_counterparty(self, request):
        """طرف حساب را به داشبورد اختصاصی‌اش هدایت می‌کند."""
        try:
            cp = getattr(request.user, 'counterparty_account', None)
        except Exception:
            return None
        if not cp:
            return None
        # مسیر مجاز برای طرف حساب
        if any(request.path.startswith(p) for p in _COUNTERPARTY_ALLOWED_PREFIXES):
            return None
        # سایر مسیرها → ریدایرکت به داشبورد
        return redirect('counterparty_dashboard')

    def _is_exempt(self, request):
        return any(request.path.startswith(p) for p in _SESSION_EXEMPT_PREFIXES)

    def _record_logout(self, user, session_key, reason):
        try:
            from .models import LoginRecord
            LoginRecord.objects.filter(
                user=user,
                session_key=session_key,
                logout_at__isnull=True,
            ).update(logout_at=timezone.now(), logout_reason=reason)
        except Exception:
            pass

    def _validate(self, request):
        now = time.time()
        session_key = request.session.session_key or ''
        user = request.user

        inactivity_timeout, allow_multi = _get_session_settings()

        # بررسی بی‌فعالیت
        last_activity = request.session.get('_last_activity')
        if last_activity is not None and now - last_activity > inactivity_timeout:
            self._record_logout(user, session_key, 'inactivity')
            logout(request)
            messages.warning(
                request,
                'به دلیل عدم فعالیت، نشست شما منقضی شد. لطفاً دوباره وارد شوید.',
            )
            return redirect(settings.LOGIN_URL)

        # بررسی ورود از دستگاه دیگر
        # اولویت: تنظیم شخصی کاربر > تنظیم سراسری
        per_user = getattr(getattr(user, 'profile', None), 'multi_session_override', None)
        effective_allow_multi = per_user if per_user is not None else allow_multi
        if not effective_allow_multi and session_key:
            try:
                from .models import UserSession
                stored = UserSession.objects.get(user=user)
                if stored.session_key != session_key:
                    self._record_logout(user, session_key, 'forced')
                    logout(request)
                    messages.warning(
                        request,
                        'حساب شما از دستگاه دیگری وارد شده است. لطفاً دوباره وارد شوید.',
                    )
                    return redirect(settings.LOGIN_URL)
            except Exception:
                pass

        request.session['_last_activity'] = now

        # به‌روزرسانی آخرین فعالیت در UserSession — حداکثر هر ۶۰ ثانیه یک‌بار
        if now - request.session.get('_us_synced', 0) > 60:
            try:
                from .models import UserSession
                from django.utils import timezone as _tz
                xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
                _ip = (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or None
                UserSession.objects.filter(user=user, session_key=session_key).update(
                    last_activity_at=_tz.now(),
                    ip_address=_ip,
                )
                request.session['_us_synced'] = now
            except Exception:
                pass

        return None


class SMSOTPMiddleware:
    """
    بعد از login موفق، اگر کاربر SMS MFA فعال داشته باشد،
    تا تأیید OTP پیامکی، او را به صفحه تأیید هدایت می‌کند.
    اگر پیامک غیرفعال باشد (sms_provider='disabled')، هیچ کاری نمی‌کند.
    """

    _EXEMPT = ('/accounts/', '/admin/', '/static/', '/media/', '/sms-verify/', '/mfa/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not any(request.path.startswith(p) for p in self._EXEMPT)
            and request.session.get('sms_mfa_pending')
        ):
            from django.urls import reverse as _rev
            return redirect(_rev('sms_otp_verify'))
        return self.get_response(request)


class EnforceCustomerPasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            def _normalize_prefix(url):
                normalized = f"/{(url or '').lstrip('/')}"
                if normalized != '/' and not normalized.endswith('/'):
                    normalized = f'{normalized}/'
                return normalized

            password_change_url = reverse('profile_password_change')
            password_cancel_url = reverse('profile_password_cancel')
            login_url = reverse('login')
            logout_url = reverse('logout')
            static_url = _normalize_prefix(settings.STATIC_URL)
            media_url = _normalize_prefix(settings.MEDIA_URL)

            exempt_paths = {
                password_change_url,
                password_cancel_url,
                login_url,
                logout_url,
            }

            is_exempt = (
                request.path == password_change_url
                or request.path == password_cancel_url
                or request.path == login_url
                or request.path == logout_url
                or request.path.startswith('/admin/')
                or request.path.startswith(static_url)
                or request.path.startswith(media_url)
                or request.path in exempt_paths
            )

            if not is_exempt:
                # سوپرادمین هرگز مجبور به تغییر رمز نمی‌شود
                if request.user.is_superuser:
                    return self.get_response(request)
                profile = getattr(request.user, 'profile', None)
                if profile and profile.force_password_change:
                    request.session['show_initial_password_change_note'] = True
                    messages.warning(request, 'برای ادامه، ابتدا باید رمز عبور خود را تغییر دهید.')
                    return redirect('profile_password_change')

        return self.get_response(request)
