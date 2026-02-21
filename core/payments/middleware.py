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
            exempt_paths = {
                password_change_url,
                settings.LOGIN_URL,
                '/accounts/logout/',
                '/admin/',
            }
            is_exempt = (
                request.path == password_change_url
                or request.path.startswith('/admin/')
                or request.path.startswith(settings.STATIC_URL)
                or request.path.startswith(settings.MEDIA_URL)
                or request.path in exempt_paths
            )
            if not is_exempt:
                profile = getattr(request.user, 'profile', None)
                if profile and profile.role == 'customer' and profile.force_password_change:
                    messages.warning(request, 'برای ادامه، ابتدا باید رمز عبور خود را تغییر دهید.')
                    return redirect('profile_password_change')

        return self.get_response(request)
