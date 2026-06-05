from django.utils import timezone

from django.urls import reverse
from django.conf import settings
from zoneinfo import ZoneInfo

from .models import LoginAdvertisement, PaymentRecord, InvoiceRecord, UserProfile


STAFF_ROLES = {'staff', 'finance', 'finance_manager', 'commercial', 'commercial_manager', 'sales', 'sales_manager', 'data_entry'}
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
        if user.profile.role in {'sales', 'sales_manager', 'commercial_manager', 'finance_manager'}:
            return True
        return bool(user.profile.can_view_invoices or user.profile.can_upload_invoices)
    except UserProfile.DoesNotExist:
        return False


_GROUP_META = {
    'main':      {'label': 'صفحات اصلی',    'icon': '🏠', 'order': 0},
    'documents': {'label': 'بررسی اسناد',   'icon': '📋', 'order': 1},
    'customers': {'label': 'مشتریان',       'icon': '👥', 'order': 2},
    'commercial':{'label': 'تجاری',         'icon': '📦', 'order': 3},
    'finance':   {'label': 'مالی',          'icon': '💰', 'order': 4},
    'admin':     {'label': 'مدیریت',        'icon': '⚙️', 'order': 5},
    'account':   {'label': 'حساب من',       'icon': '👤', 'order': 6},
}


def _nav_item(label, url_name, key, group='main', icon=''):
    return {
        'label': label,
        'url': reverse(url_name),
        'key': key,
        'group': group,
        'icon': icon,
    }


def _group_nav_items(items):
    from collections import defaultdict

    groups_dict = defaultdict(list)
    for item in items:
        groups_dict[item['group']].append(item)

    nav_groups = []
    for gkey in sorted(_GROUP_META, key=lambda k: _GROUP_META[k]['order']):
        if gkey not in groups_dict:
            continue
        meta = _GROUP_META[gkey]
        nav_groups.append({
            'key': gkey,
            'label': meta['label'],
            'icon': meta['icon'],
            'items': groups_dict[gkey],
            'is_main': gkey == 'main',
        })
    return nav_groups


def app_navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {'app_nav_items': [], 'app_nav_role_label': '', 'app_nav_user_display': ''}

    role = _role_for_nav(user)
    is_staff_user = user.is_staff or user.is_superuser or role in STAFF_ROLES or role == 'admin'

    # طرف حساب — منوی اختصاصی
    cp = getattr(user, 'counterparty_account', None)
    if cp and not is_staff_user:
        cp_items = [
            _nav_item('داشبورد طرف حساب', 'counterparty_dashboard', 'cp_dashboard'),
            _nav_item('ویرایش مشخصات', 'profile_edit', 'profile', 'account'),
            _nav_item('تغییر رمز عبور', 'profile_password_change', 'password', 'account'),
        ]
        role_label = f'طرف حساب: {cp.name}'
        user_display = user.get_full_name().strip() or user.username
        return {
            'app_nav_items': cp_items,
            'app_nav_groups': _group_nav_items(cp_items),
            'app_nav_role_label': role_label,
            'app_nav_user_display': user_display,
        }

    items = [_nav_item('داشبورد', 'submit', 'submit', 'main', '🏠')]

    if role == 'customer':
        items.extend([
            _nav_item('ثبت فیش جدید',    'payment_create',        'payment_create',         'main',       '📤'),
            _nav_item('فاکتورها',          'invoices_dashboard',     'invoices',               'commercial', '🧾'),
            _nav_item('لیست قیمت',         'price_lists',            'price_lists',            'commercial', '💲'),
            _nav_item('سفارش‌ها',           'orders',                 'orders',                 'commercial', '🛒'),
            _nav_item('پیش‌فاکتورها',       'proformas',              'proformas',              'commercial', '📝'),
            _nav_item('برنامه واریز من',   'customer_daily_payments', 'customer_daily_payments','finance',    '📅'),
        ])
    else:
        # ── اسناد ───────────────────────────────────────────────
        items.extend([
            _nav_item('صف کاری اسناد',     'submit',           'payment_queue',   'documents', '📥'),
            _nav_item('سوابق اسناد',        'payment_history',  'payment_history', 'documents', '🗂️'),
        ])
        # ── مشتریان ──────────────────────────────────────────────
        items.append(_nav_item('لیست مشتریان', 'customers_list', 'customers', 'customers', '👥'))

        # ── تجاری ────────────────────────────────────────────────
        COMMERCIAL_ROLES = {'commercial', 'commercial_manager', 'sales', 'sales_manager', 'finance', 'finance_manager'}
        if user.is_superuser or _can_view_invoices_nav(user):
            items.append(_nav_item('فاکتورها',     'invoices_dashboard',    'invoices',      'commercial', '🧾'))
        if user.is_superuser or role in COMMERCIAL_ROLES:
            items.append(_nav_item('لیست قیمت',    'price_lists',           'price_lists',   'commercial', '💲'))
            items.append(_nav_item('سفارش‌ها',      'orders',                'orders',        'commercial', '🛒'))
            items.append(_nav_item('پیش‌فاکتورها',  'proformas',             'proformas',     'commercial', '📝'))
        if user.is_superuser or role in {'sales', 'sales_manager'}:
            items.append(_nav_item('داشبورد فروش', 'sales_expert_dashboard', 'sales_dashboard', 'commercial', '📊'))

        # ── مالی ─────────────────────────────────────────────────
        if is_staff_user:
            items.append(_nav_item('برنامه واریز', 'daily_payment_plans', 'daily_payments', 'finance', '📅'))
        if user.is_superuser or role == 'finance_manager':
            items.append(_nav_item('تفویض تأیید نهایی', 'final_approval_delegation', 'delegation', 'finance', '✍️'))

        # ── مدیریت ───────────────────────────────────────────────
        if user.is_superuser or role == 'sales_manager':
            items.append(_nav_item('تخصیص مشتریان فروش', 'sales_assignments', 'sales_assignments', 'admin', '🔗'))
        if user.is_superuser:
            items.extend([
                _nav_item('مدیریت کاربران',       'users_manage',            'users',              'admin', '👤'),
                _nav_item('مدیریت طرف حساب‌ها',   'counterparty_manage_list','counterparties_full','admin', '🏢'),
                _nav_item('تست خوانش فیش',        'receipt_reader_test',     'receipt_reader',     'admin', '🔍'),
            ])
        elif not user.is_superuser and is_staff_user:
            items.append(_nav_item('تایید مشخصات', 'users_manage', 'profile_changes', 'admin', '✅'))

    # ── حساب من ──────────────────────────────────────────────────
    items.extend([
        _nav_item('ویرایش مشخصات',         'profile_edit',          'profile',   'account', '✏️'),
        _nav_item('تغییر رمز عبور',         'profile_password_change','password', 'account', '🔑'),
        _nav_item('احراز هویت دو مرحله‌ای', 'mfa_home',              'mfa',       'account', '🛡️'),
        _nav_item('تأیید پیامکی',           'sms_mfa_setup',         'sms_mfa',   'account', '📱'),
    ])

    role_label = {
        'admin':              'مدیر سیستم',
        'customer':           'مشتری',
        'commercial':         'واحد بازرگانی',
        'commercial_manager': 'مدیر بازرگانی',
        'finance':            'واحد مالی',
        'finance_manager':    'مدیر مالی',
        'sales':              'فروش',
        'sales_manager':      'مدیر فروش',
        'data_entry':         'تکمیل اطلاعات',
        'staff':              'کارمند',
        'counterparty':       'طرف حساب',
    }.get(role, 'کاربر')

    # گروه‌بندی آیتم‌ها برای dropdown منو
    return {
        'app_nav_items':  items,
        'app_nav_groups': _group_nav_items(items),
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

    elif role in ('finance', 'finance_manager', 'commercial', 'commercial_manager', 'sales_manager', 'staff'):
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
