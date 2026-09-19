"""
هسته‌ی منطق «ورود کارمند به‌عنوان مشتری» (impersonation).

طراحی امنیتی: کاربر واقعیِ واردشده به سامانه (وضعیت احراز هویت Django) هرگز عوض
نمی‌شود — همیشه همان کارمند واقعی می‌ماند و از همان نشست/رمز/MFA خودش استفاده
می‌کند. فقط `request.user` برای طول همان درخواست با شیء کاربر مشتری جایگزین
می‌شود (توسط ImpersonationMiddleware)، و یک ارجاع به کارمند واقعی روی همان شیء
(`impersonator`) گذاشته می‌شود. این یعنی:
- تمام منطق موجود «چه چیزی برای این کاربر قابل‌مشاهده/مجاز است» در سراسر برنامه
  بدون هیچ تغییری، دقیقاً مطابق دسترسی واقعی مشتری کار می‌کند.
- توابع مرکزی ثبت سابقه/اعلان (`_log_activity`, `_notify_users` در views.py) با
  کمک `_real_actor()` کارمند واقعی را به‌عنوان actor ثبت می‌کنند، نه هویت مشتری.
"""
import time

from django.utils import timezone

from .models import CustomerImpersonationSession, UserNotification

IMPERSONATION_SESSION_KEY = 'impersonation_session_id'
IMPERSONATION_LAST_ACTIVITY_KEY = 'impersonation_last_activity'
ROLE_CONFIRMED_SESSION_KEY = 'role_confirmed'


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or None


def start_impersonation(request, staff_user, customer_user):
    """
    یک جلسه‌ی جانمایی جدید می‌سازد و بلافاصله یک اطلاع‌رسانی دوگانه (داخل‌برنامه‌ای +
    پیامک، در صورت فعال بودن) به خود مشتری می‌فرستد که کارمند به حسابش متصل شده.
    """
    session = CustomerImpersonationSession.objects.create(
        staff_user=staff_user,
        customer_user=customer_user,
        session_key=request.session.session_key or '',
        ip_address=_client_ip(request),
    )
    request.session[IMPERSONATION_SESSION_KEY] = session.id
    request.session[IMPERSONATION_LAST_ACTIVITY_KEY] = time.time()
    request.session[ROLE_CONFIRMED_SESSION_KEY] = True

    staff_name = (staff_user.get_full_name() or staff_user.username).strip()
    now_text = timezone.localtime(session.started_at).strftime('%H:%M')

    # جلوگیری از import چرخه‌ای — views.py در سطح ماژول این فایل را import می‌کند
    from .views import _notify_users

    _notify_users(
        [customer_user],
        'اتصال کارمند پشتیبانی به حساب شما',
        f'کارمند «{staff_name}» برای راهنمایی/پشتیبانی به حساب کاربری شما در سامانه متصل شد (ساعت {now_text}).',
        category=UserNotification.CATEGORY_SYSTEM,
        actor=staff_user,
        sms_message=f'کارمند «{staff_name}» برای پشتیبانی به حساب کاربری شما در سامانه متصل شد.',
    )
    return session


def end_impersonation(request, reason=CustomerImpersonationSession.END_REASON_MANUAL):
    """جلسه‌ی جانمایی فعلی (اگر باشد) را می‌بندد و از نشست پاک می‌کند."""
    session_id = request.session.pop(IMPERSONATION_SESSION_KEY, None)
    request.session.pop(IMPERSONATION_LAST_ACTIVITY_KEY, None)
    if not session_id:
        return None
    CustomerImpersonationSession.objects.filter(
        id=session_id, ended_at__isnull=True,
    ).update(ended_at=timezone.now(), end_reason=reason)
    return session_id


def get_active_impersonation(request):
    """جلسه‌ی جانمایی فعال (اگر باشد) را برمی‌گرداند — بدون اعمال آن روی request.user."""
    session_id = request.session.get(IMPERSONATION_SESSION_KEY)
    if not session_id:
        return None
    return (
        CustomerImpersonationSession.objects
        .select_related('staff_user', 'staff_user__profile', 'customer_user', 'customer_user__profile')
        .filter(id=session_id, ended_at__isnull=True)
        .first()
    )


class ImpersonationMiddleware:
    """
    اگر نشستِ فعلی یک جلسه‌ی جانمایی فعال دارد و کاربر واقعیِ واردشده همان کارمندی
    است که آن را شروع کرده، `request.user` را (فقط برای طول همین درخواست، بدون
    تغییر وضعیت واقعی نشست/احراز هویت Django) با کاربر مشتری جایگزین می‌کند و
    ارجاع کارمند واقعی را روی `request.user.impersonator` می‌گذارد.

    باید همیشه بعد از AuthenticationMiddleware (که request.user را می‌سازد) و قبل
    از SingleSessionMiddleware / SMSOTPMiddleware / EnforceCustomerPasswordChangeMiddleware
    در MIDDLEWARE قرار بگیرد — چون آن سه میان‌افزار نباید روی هویت جایگزین‌شده‌ی
    مشتری اعمال شوند (وگرنه ممکن است نشست واقعی مشتری را قطع کنند یا او را مجبور
    به تغییر رمز کنند).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_impersonating = False
        request.impersonation_session = None

        session_id = request.session.get(IMPERSONATION_SESSION_KEY)
        if session_id and getattr(request.user, 'is_authenticated', False):
            imp = get_active_impersonation(request)
            if imp and imp.staff_user_id == request.user.id and imp.customer_user_id:
                if self._is_inactive(request):
                    # پس از مدت بی‌فعالیت، جانمایی به‌صورت خودکار پایان می‌یابد
                    end_impersonation(request, reason=CustomerImpersonationSession.END_REASON_INACTIVITY)
                else:
                    customer_user = imp.customer_user
                    if customer_user and customer_user.is_active:
                        customer_user.impersonator = imp.staff_user
                        request.user = customer_user
                        request.is_impersonating = True
                        request.impersonation_session = imp
                        request.session[IMPERSONATION_LAST_ACTIVITY_KEY] = time.time()
                    else:
                        # مشتری هدف دیگر فعال نیست — جلسه را به‌صورت اجباری پایان بده
                        end_impersonation(request, reason=CustomerImpersonationSession.END_REASON_FORCED)
            else:
                # ناسازگاری نشست/کاربر — پاک‌سازی امن به‌جای اعمال جانمایی نامعتبر
                request.session.pop(IMPERSONATION_SESSION_KEY, None)
                request.session.pop(IMPERSONATION_LAST_ACTIVITY_KEY, None)

        return self.get_response(request)

    def _is_inactive(self, request):
        last = request.session.get(IMPERSONATION_LAST_ACTIVITY_KEY)
        if last is None:
            return False
        from .middleware import _get_session_settings
        timeout_seconds, _ = _get_session_settings()
        return (time.time() - last) > timeout_seconds
