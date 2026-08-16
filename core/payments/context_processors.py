from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings
from django.db.models import Q
from zoneinfo import ZoneInfo

from .models import FinalApprovalDelegate, LoginAdvertisement, ReconciliationThread, SystemSettings, UserNotification, UserProfile, WarrantyClaim


STAFF_ROLES = {'staff', 'finance', 'finance_manager', 'commercial', 'commercial_manager', 'sales', 'sales_manager', 'data_entry', 'warranty', 'warranty_manager'}
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


def _profile_for_nav(user):
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        return None


def _can_view_invoices_nav(user):
    if user.is_superuser:
        return True
    if not user.is_authenticated:
        return False
    try:
        # مشتریان همگی دسترسی یکسان به مشاهده فاکتورهای خودشان دارند.
        if user.profile.role == 'customer':
            return True
        if user.profile.role in {'sales', 'sales_manager', 'commercial_manager', 'finance_manager'}:
            return True
        return bool(user.profile.can_view_invoices or user.profile.can_upload_invoices)
    except UserProfile.DoesNotExist:
        return False


ACCESS_DEPARTMENT_MANAGER_ROLES = {'commercial_manager', 'finance_manager', 'sales_manager', 'warranty_manager'}


def _can_manage_access_nav(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return user.profile.role in ACCESS_DEPARTMENT_MANAGER_ROLES
    except UserProfile.DoesNotExist:
        return False


def _can_see_pending_final_nav(user, role):
    if user.is_superuser or role == 'finance_manager':
        return True
    return FinalApprovalDelegate.objects.filter(delegated_user=user, is_active=True).exists()


def _can_access_reconciliation_nav(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        role = user.profile.role
    except UserProfile.DoesNotExist:
        role = ''
    # کلیه کارکنان و مشتریان لینک مغایرت‌گیری را می‌بینند
    if role == 'customer':
        return True
    return role in STAFF_ROLES


_RECON_UNREAD_TTL = 30  # seconds


def recon_unread_cache_key(user_id):
    return f'recon_unread_{user_id}'


def _reconciliation_unread_count_nav(user):
    if not _can_access_reconciliation_nav(user):
        return 0
    cache_key = recon_unread_cache_key(user.id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    count = 0
    threads = (
        ReconciliationThread.objects
        .filter(Q(customer=user) | Q(staff_participants=user))
        .prefetch_related('read_states')
        .distinct()
    )
    if user.is_superuser:
        threads = ReconciliationThread.objects.prefetch_related('read_states').all()
    for thread in threads:
        state = next((item for item in thread.read_states.all() if item.user_id == user.id), None)
        messages = thread.messages.exclude(sender_id=user.id)
        if state:
            messages = messages.filter(created_at__gt=state.last_read_at)
        count += messages.count()
    cache.set(cache_key, count, _RECON_UNREAD_TTL)
    return count


_GROUP_META = {
    'main':      {'label': 'داشبورد',                    'icon': '🏠',  'order': 0},
    'documents': {'label': 'اسناد',                      'icon': '📋',  'order': 1},
    'customers': {'label': 'مشتریان',                    'icon': '👥',  'order': 2},
    'business':  {'label': 'بازرگانی',                   'icon': '🏦',  'order': 3},
    'sales':     {'label': 'فروش',                       'icon': '📦',  'order': 4},
    'warranty':  {'label': 'گارانتی و خدمات پس از فروش', 'icon': '🛡️', 'order': 5},
    'finance':   {'label': 'مالی',                       'icon': '💰',  'order': 6},
    'system':    {'label': 'عملیات سیستمی',               'icon': '⚙️', 'order': 7},
    'account':   {'label': 'حساب من',                    'icon': '👤',  'order': 8},
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


def _business_card_context(user, profile, role_label, display_name, counterparty=None):
    organization = getattr(profile, 'organization', '') or ''
    if counterparty and not organization:
        organization = counterparty.name
    location_parts = [
        (getattr(profile, 'city', '') or '').strip(),
        (getattr(profile, 'province', '') or '').strip(),
    ]
    return {
        'app_nav_card': {
            'display_name': display_name,
            'username': user.username,
            'role_label': role_label,
            'organization': organization,
            'phone': getattr(profile, 'phone', '') or '',
            'mobile': getattr(profile, 'mobile', '') or '',
            'email': user.email or '',
            'location': ' / '.join(part for part in location_parts if part),
            'representative_name': getattr(profile, 'representative_name', '') or '',
            'representative_mobile': getattr(profile, 'representative_mobile', '') or '',
            'delegate_sms_to_representative': bool(getattr(profile, 'delegate_sms_to_representative', False)),
        }
    }


def app_navigation(request):
    user = request.user
    if not user.is_authenticated:
        return {'app_nav_items': [], 'app_nav_role_label': '', 'app_nav_user_display': '', 'app_nav_is_customer': False}

    role = _role_for_nav(user)
    is_staff_user = user.is_staff or user.is_superuser or role in STAFF_ROLES or role == 'admin'
    profile = _profile_for_nav(user)
    try:
        app_logo_url = SystemSettings.load().system_logo_url
    except Exception:
        app_logo_url = ''

    # طرف حساب — منوی اختصاصی
    cp = getattr(user, 'counterparty_account', None)
    if cp and not is_staff_user:
        cp_items = [
            _nav_item('داشبورد', 'counterparty_dashboard', 'cp_dashboard'),
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
            'app_nav_avatar_url': profile.avatar_url if profile else '',
            'app_nav_avatar_icon': profile.avatar_icon if profile else '👤',
            'app_nav_avatar_class': profile.avatar_class if profile else 'avatar-neutral_1',
            'app_nav_reconciliation_unread': _reconciliation_unread_count_nav(user),
            'app_nav_logo_url': app_logo_url,
            **_business_card_context(user, profile, role_label, user_display, counterparty=cp),
        }

    items = [_nav_item('داشبورد', 'submit', 'submit', 'main', '🏠')]

    if role == 'customer':
        items.extend([
            _nav_item('ثبت فیش',        'payment_create',         'payment_create',          'main', '📤'),
            _nav_item('لیست قیمت',      'price_lists',            'price_lists',             'main', '💲'),
            _nav_item('سفارش گذاری',     'orders',                 'orders',                  'main', '🛒'),
            _nav_item('پیش فاکتور',      'proformas',              'proformas',               'main', '📝'),
            _nav_item('فاکتور فروش',     'invoices_dashboard',     'invoices',                'main', '🧾'),
            _nav_item('برنامه واریز',    'customer_daily_payments','customer_daily_payments', 'main', '📅'),
            _nav_item('مغایرت‌گیری',      'reconciliation_center',  'reconciliation',          'main', '💬'),
        ])
        if SystemSettings.load().customer_warranty_menu_enabled:
            items.extend([
                _nav_item('درخواست گارانتی', 'warranty_new',           'warranty_new',            'warranty', '🛡️'),
                _nav_item('درخواست‌های من',   'warranty_my_claims',     'warranty_my',             'warranty', '📋'),
                _nav_item('پیگیری وضعیت',    'warranty_track',         'warranty_track',          'warranty', '🔍'),
            ])
    else:
        items.append(_nav_item('صف کاری اسناد', 'submit', 'payment_queue', 'documents', '📥'))
        if _can_see_pending_final_nav(user, role):
            items.append(_nav_item('در انتظار تأیید نهایی', 'pending_final_approval', 'pending_final', 'documents', '⏳'))
        items.append(_nav_item('سوابق اسناد', 'payment_history', 'payment_history', 'documents', '🗂️'))
        items.append(_nav_item('مشتریان', 'customers_list', 'customers', 'customers', '👥'))

        COMMERCIAL_ROLES = {'commercial', 'commercial_manager', 'sales', 'sales_manager', 'finance', 'finance_manager'}
        if is_staff_user:
            items.append(_nav_item('برنامه واریز', 'daily_payment_plans', 'daily_payments', 'business', '📅'))
        if user.is_superuser or role in COMMERCIAL_ROLES:
            items.append(_nav_item('اطلاعیه فیش روزانه', 'daily_payment_notices', 'daily_payment_notices', 'business', '📣'))

        if user.is_superuser or role in COMMERCIAL_ROLES:
            items.append(_nav_item('لیست قیمت', 'price_lists', 'price_lists', 'sales', '💲'))
            items.append(_nav_item('سفارش‌ها', 'orders', 'orders', 'sales', '🛒'))
            items.append(_nav_item('پیشنهاد فروش', 'proformas', 'proformas', 'sales', '📝'))
        if user.is_superuser or _can_view_invoices_nav(user):
            items.append(_nav_item('فاکتور فروش', 'invoices_dashboard', 'invoices', 'sales', '🧾'))
        if user.is_superuser or role in {'sales', 'sales_manager'}:
            items.append(_nav_item('داشبورد فروش', 'sales_expert_dashboard', 'sales_dashboard', 'sales', '📊'))
        if user.is_superuser or role in {'sales_manager', 'sales', 'commercial_manager'}:
            items.append(_nav_item('درخواست‌های نمایندگی', 'agency_applications', 'agency', 'sales', '🤝'))

        # ── گارانتی ───────────────────────────────────────────────────────────
        if user.is_superuser or role in {'warranty', 'warranty_manager'}:
            open_count = WarrantyClaim.objects.filter(status__in=[
                WarrantyClaim.STATUS_SUBMITTED, WarrantyClaim.STATUS_REVIEWING,
                WarrantyClaim.STATUS_INFO_NEEDED, WarrantyClaim.STATUS_APPROVED,
                WarrantyClaim.STATUS_IN_PROGRESS,
            ]).count()
            items.append(_nav_item(
                f'مدیریت گارانتی' + (f' ({open_count})' if open_count else ''),
                'warranty_staff_list', 'warranty_staff', 'warranty', '🛡️',
            ))
        # کارکنان دیگر هم می‌توانند درخواست ثبت کنند
        if is_staff_user:
            items.extend([
                _nav_item('ثبت درخواست گارانتی', 'warranty_new',    'warranty_new_staff', 'warranty', '📝'),
                _nav_item('درخواست‌های من',        'warranty_my_claims', 'warranty_my_staff', 'warranty', '📋'),
            ])

        if user.is_superuser or role == 'finance_manager':
            items.append(_nav_item('تفویض تایید اسناد', 'final_approval_delegation', 'delegation', 'finance', '✍️'))
        if user.is_superuser:
            items.append(_nav_item('مدیریت طرف حساب‌ها', 'counterparty_manage_list', 'counterparties_full', 'finance', '🏢'))
        if user.is_superuser or _can_access_reconciliation_nav(user):
            items.append(_nav_item('مغایرت‌گیری', 'reconciliation_center', 'reconciliation', 'finance', '💬'))

        if user.is_superuser or role == 'sales_manager':
            items.append(_nav_item('تخصیص مشتریان فروش', 'sales_assignments', 'sales_assignments', 'system', '🔗'))
        if _can_manage_access_nav(user):
            items.append(_nav_item('مدیریت دسترسی‌ها', 'access_management', 'access_management', 'system', '🔐'))
        if user.is_superuser:
            items.extend([
                _nav_item('مدیریت کاربران', 'users_manage', 'users', 'system', '👤'),
                _nav_item('تنظیم لوگو', 'system_logo_settings', 'system_logo_settings', 'system', '🖼'),
                _nav_item('تست خوانش فیش', 'receipt_reader_test', 'receipt_reader', 'system', '🔍'),
            ])
        elif not user.is_superuser and is_staff_user:
            items.append(_nav_item('تایید مشخصات', 'users_manage', 'profile_changes', 'system', '✅'))

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
        'warranty':           'کارشناس گارانتی',
        'warranty_manager':   'مدیر گارانتی',
        'counterparty':       'طرف حساب',
    }.get(role, 'کاربر')

    customer_bottom_nav_items = []
    if role == 'customer':
        bottom_keys = ['submit', 'payment_create', 'price_lists', 'invoices', 'orders']
        items_by_key = {item['key']: item for item in items}
        customer_bottom_nav_items = [items_by_key[key] for key in bottom_keys if key in items_by_key]

    # گروه‌بندی آیتم‌ها برای dropdown منو
    return {
        'app_nav_items':  items,
        'app_nav_groups': _group_nav_items(items),
        'app_nav_is_customer': role == 'customer',
        'app_nav_customer_bottom_items': customer_bottom_nav_items,
        'app_nav_role_label': role_label,
        'app_nav_user_display': user.get_full_name().strip() or user.username,
        'app_nav_avatar_url': profile.avatar_url if profile else '',
        'app_nav_avatar_icon': profile.avatar_icon if profile else '👤',
        'app_nav_avatar_class': profile.avatar_class if profile else 'avatar-neutral_1',
        'app_nav_reconciliation_unread': _reconciliation_unread_count_nav(user),
        'app_nav_logo_url': app_logo_url,
        **_business_card_context(user, profile, role_label, user.get_full_name().strip() or user.username),
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
    Context processor providing the unread in-app notification badge/list for the
    nav bell. Sourced from UserNotification so it matches /api/notifications/ —
    the JS poller overwrites this on load, but the first paint must agree with it.
    """
    empty = {'total': 0, 'items': []}

    if not request.user.is_authenticated:
        return {'unread_notifications': empty}

    notifications = UserNotification.objects.filter(user=request.user, is_read=False)
    items = [
        {'id': n.id, 'title': n.title, 'message': n.message, 'url': n.resolved_url}
        for n in notifications[:5]
    ]
    return {'unread_notifications': {'total': notifications.count(), 'items': items}}
