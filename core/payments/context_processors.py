from django.utils import timezone

from django.urls import reverse
from django.conf import settings
from zoneinfo import ZoneInfo

from .models import LoginAdvertisement, PaymentRecord, InvoiceRecord, UserProfile


STAFF_ROLES = {'staff', 'finance', 'commercial', 'sales', 'data_entry'}
DISPLAY_TIME_ZONE = ZoneInfo(getattr(settings, 'APP_DISPLAY_TIME_ZONE', 'Asia/Tehran'))


def _role_for_nav(user):
    if not user.is_authenticated:
        return ''
    if user.is_superuser:
        return 'admin'
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return 'staff' if user.is_staff else 'customer'


def _can_view_invoices_nav(user):
    if user.is_superuser:
        return True
    if not user.is_authenticated:
        return False
    try:
        return bool(user.profile.can_view_invoices or user.profile.can_upload_invoices)
    except UserProfile.DoesNotExist:
        return False


def _nav_item(label, url_name, key, group='main'):
    return {
        'label': label,
        'url': reverse(url_name),
        'key': key,
        'group': group,
    }


def app_navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {'app_nav_items': [], 'app_nav_role_label': '', 'app_nav_user_display': ''}

    role = _role_for_nav(user)
    is_staff_user = user.is_staff or user.is_superuser or role in STAFF_ROLES or role == 'admin'
    items = [_nav_item('داشبورد', 'submit', 'submit')]

    if role == 'customer':
        items.extend([
            _nav_item('ثبت فیش', 'payment_create', 'payment_create'),
            _nav_item('فاکتورها', 'invoices_dashboard', 'invoices'),
            _nav_item('لیست قیمت', 'price_lists', 'price_lists'),
            _nav_item('پیش فاکتورها', 'proformas', 'proformas'),
            _nav_item('برنامه واریز من', 'customer_daily_payments', 'customer_daily_payments', 'finance'),
        ])
    else:
        items.extend([
            _nav_item('صف کاری اسناد', 'submit', 'payment_queue'),
            _nav_item('سوابق اسناد', 'payment_history', 'payment_history'),
            _nav_item('مشتریان', 'customers_list', 'customers', 'customers'),
        ])
        if user.is_superuser or _can_view_invoices_nav(user):
            items.append(_nav_item('فاکتورها', 'invoices_dashboard', 'invoices', 'documents'))
        if user.is_superuser or role in {'commercial', 'sales', 'finance'}:
            items.append(_nav_item('لیست قیمت', 'price_lists', 'price_lists', 'documents'))
        if user.is_superuser or role in {'commercial', 'sales', 'finance'}:
            items.append(_nav_item('پیش فاکتورها', 'proformas', 'proformas', 'documents'))
        if is_staff_user:
            items.append(_nav_item('برنامه واریز', 'daily_payment_plans', 'daily_payments', 'finance'))
            if not user.is_superuser:
                items.append(_nav_item('تایید مشخصات', 'users_manage', 'profile_changes', 'admin'))
        if user.is_superuser:
            items.extend([
                _nav_item('مدیریت کاربران', 'users_manage', 'users', 'admin'),
                _nav_item('طرف حساب‌ها', 'counterparties_manage', 'counterparties', 'admin'),
            ])

    items.extend([
        _nav_item('ویرایش مشخصات', 'profile_edit', 'profile', 'account'),
        _nav_item('تغییر رمز عبور', 'profile_password_change', 'password', 'account'),
    ])

    role_label = {
        'admin': 'مدیر سیستم',
        'customer': 'مشتری',
        'finance': 'مالی',
        'commercial': 'بازرگانی',
        'sales': 'فروش',
        'data_entry': 'تکمیل اطلاعات',
        'staff': 'کارمند',
    }.get(role, 'کاربر')

    return {
        'app_nav_items': items,
        'app_nav_role_label': role_label,
        'app_nav_user_display': user.get_full_name().strip() or user.username,
    }


def login_ads(request):
    today = timezone.localdate()
    active_ads = (
        LoginAdvertisement.objects
        .filter(is_visible=True, start_date__lte=today, end_date__gte=today)
        .order_by('slot')
    )
    by_slot = {ad.slot: ad for ad in active_ads}
    slot_ads = [{'slot': slot, 'ad': by_slot.get(slot)} for slot in (1, 2, 3, 4)]
    return {
        'login_ads_by_slot': by_slot,
        'login_slot_ads': slot_ads,
    }


def unread_notifications(request):
    """
    Context processor to provide unread document counts for the notification bell.
    """
    unread_counts = {
        'payments': 0,
        'invoices': 0,
        'total': 0,
        'items': [],
    }

    if not request.user.is_authenticated:
        return {'unread_notifications': unread_counts}

    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return {'unread_notifications': unread_counts}

    role = profile.role

    if role == 'customer':
        # For customers: count documents they haven't seen
        unread_counts['payments'] = PaymentRecord.objects.filter(
            user=request.user,
            customer_seen_at__isnull=True
        ).count()

        unread_counts['invoices'] = InvoiceRecord.objects.filter(
            customer=request.user,
            customer_seen_at__isnull=True
        ).count()

    elif role in ('finance', 'commercial', 'staff'):
        # For staff: count documents created today that haven't been seen by anyone
        # Or count documents with recent status changes
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.localdate(timezone=DISPLAY_TIME_ZONE)
        tomorrow = today + timedelta(days=1)

        # Count recent payments (created today)
        unread_counts['payments'] = PaymentRecord.objects.filter(
            created_at__date=today
        ).count()

        # Count recent invoices
        unread_counts['invoices'] = InvoiceRecord.objects.filter(
            created_at__date=today
        ).count()

    unread_counts['total'] = unread_counts['payments'] + unread_counts['invoices']

    return {'unread_notifications': unread_counts}
