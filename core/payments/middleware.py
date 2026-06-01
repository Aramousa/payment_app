import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

_SESSION_EXEMPT_PREFIXES = ('/accounts/', '/admin/', '/static/', '/media/')
_COUNTERPARTY_ALLOWED_PREFIXES = ('/counterparty/', '/accounts/', '/admin/', '/static/', '/media/', '/profile/')

# کش ساده برای timeout — هر ۶۰ ثانیه از دیتابیس می‌خواند
_timeout_cache = {'value': None, 'ts': 0.0}


def _get_inactivity_timeout():
    now = time.monotonic()
    if _timeout_cache['value'] is None or now - _timeout_cache['ts'] > 60:
        try:
            from .models import SystemSettings
            obj = SystemSettings.load()
            _timeout_cache['value'] = obj.session_inactivity_timeout * 60
        except Exception:
            _timeout_cache['value'] = getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', 30 * 60)
        _timeout_cache['ts'] = now
    return _timeout_cache['value']


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

        # بررسی بی‌فعالیت
        last_activity = request.session.get('_last_activity')
        if last_activity is not None and now - last_activity > _get_inactivity_timeout():
            self._record_logout(user, session_key, 'inactivity')
            logout(request)
            messages.warning(
                request,
                'به دلیل عدم فعالیت، نشست شما منقضی شد. لطفاً دوباره وارد شوید.',
            )
            return redirect(settings.LOGIN_URL)

        # بررسی ورود از دستگاه دیگر
        if session_key:
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
        return None


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
