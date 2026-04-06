from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class EnforceCustomerPasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            password_change_url = reverse('profile_password_change')
            password_cancel_url = reverse('profile_password_cancel')
            static_url = settings.STATIC_URL if settings.STATIC_URL.startswith('/') else f"/{settings.STATIC_URL}"
            media_url = settings.MEDIA_URL if settings.MEDIA_URL.startswith('/') else f"/{settings.MEDIA_URL}"

            exempt_paths = {
                password_change_url,
                password_cancel_url,
                settings.LOGIN_URL,
                '/accounts/logout/',
                '/admin/',
            }

            is_exempt = (
                request.path == password_change_url
                or request.path == password_cancel_url
                or request.path.startswith('/admin/')
                or request.path.startswith(static_url)
                or request.path.startswith(media_url)
                or request.path in exempt_paths
            )

            if not is_exempt:
                profile = getattr(request.user, 'profile', None)
                if profile and profile.role == 'customer' and profile.force_password_change:
                    messages.warning(request, 'برای ادامه، ابتدا باید رمز عبور خود را تغییر دهید.')
                    return redirect('profile_password_change')

        return self.get_response(request)
