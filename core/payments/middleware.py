from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


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
                if request.user.is_superuser or request.user.is_staff:
                    return self.get_response(request)
                profile = getattr(request.user, 'profile', None)
                if profile and profile.role == 'customer' and profile.force_password_change:
                    request.session['show_initial_password_change_note'] = True
                    messages.warning(request, 'برای ادامه، ابتدا باید رمز عبور خود را تغییر دهید.')
                    return redirect('profile_password_change')

        return self.get_response(request)
