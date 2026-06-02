from django.shortcuts import redirect


def mfa_login_callback(request, next_url='/submit/'):
    """بعد از تأیید موفق MFA، کاربر را به مقصد مناسب هدایت می‌کند."""
    from payments.views import _is_counterparty_user
    if _is_counterparty_user(request.user):
        return redirect('counterparty_dashboard')
    if next_url and next_url != '/':
        return redirect(next_url)
    return redirect('submit')
