import jdatetime
import logging
import mimetypes
import random
from openpyxl import Workbook
from urllib.parse import urlencode
import json

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import DatabaseError, IntegrityError
from django.db.models import Count, Max, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.sessions.models import Session
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CounterpartyForm, CustomPasswordChangeForm, CustomerProfileUpdateForm, DailyPaymentAssignmentForm, DailyPaymentPlanForm, InvoiceCustomerNoteForm, InvoiceUploadForm, PaymentRecordForm, StaffStatusUpdateForm, UserAccountManagementForm
from .models import Counterparty, DailyPaymentAssignment, DailyPaymentPlan, InvoiceRecord, LoginAdvertisement, PaymentActivityLog, PaymentRecord, PaymentReceipt, SystemActivityLog, UserProfile


STAFF_ROLES = {'staff', 'finance', 'commercial'}
logger = logging.getLogger(__name__)
STATUS_FLAG_META = {
    PaymentRecord.STATUS_COMMERCIAL_REVIEW: ('رویت بازرگانی', 'flag-blue'),
    PaymentRecord.STATUS_FINANCE_REVIEW: ('رویت مالی', 'flag-purple'),
    PaymentRecord.STATUS_APPROVED: ('تایید شده', 'flag-green'),
    PaymentRecord.STATUS_FINAL_APPROVED: ('تایید نهایی', 'flag-green'),
    PaymentRecord.STATUS_REJECTED: ('رد شده', 'flag-red'),
    PaymentRecord.STATUS_INCOMPLETE: ('ناقص', 'flag-yellow'),
    PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL: ('عودت به بازرگانی', 'flag-blue'),
}
STATUS_PROGRESS_FLOWS = {
    PaymentRecord.STATUS_COMMERCIAL_REVIEW: [PaymentRecord.STATUS_COMMERCIAL_REVIEW],
    PaymentRecord.STATUS_FINANCE_REVIEW: [PaymentRecord.STATUS_COMMERCIAL_REVIEW, PaymentRecord.STATUS_FINANCE_REVIEW],
    PaymentRecord.STATUS_APPROVED: [PaymentRecord.STATUS_COMMERCIAL_REVIEW, PaymentRecord.STATUS_FINANCE_REVIEW, PaymentRecord.STATUS_APPROVED],
    PaymentRecord.STATUS_FINAL_APPROVED: [
        PaymentRecord.STATUS_COMMERCIAL_REVIEW,
        PaymentRecord.STATUS_FINANCE_REVIEW,
        PaymentRecord.STATUS_APPROVED,
        PaymentRecord.STATUS_FINAL_APPROVED,
    ],
    PaymentRecord.STATUS_REJECTED: [PaymentRecord.STATUS_REJECTED],
    PaymentRecord.STATUS_INCOMPLETE: [PaymentRecord.STATUS_INCOMPLETE],
    PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL: [PaymentRecord.STATUS_COMMERCIAL_REVIEW, PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL],
}
CUSTOMER_STATUSES = [
    (PaymentRecord.STATUS_PENDING, 'در حال بررسی'),
    (PaymentRecord.STATUS_FINAL_APPROVED, 'تایید نهایی'),
    (PaymentRecord.STATUS_REJECTED, 'رد شده'),
    (PaymentRecord.STATUS_INCOMPLETE, 'ناقص'),
]


def _user_role(user):
    if not user.is_authenticated:
        return ''
    if user.is_superuser:
        return 'staff'
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return 'staff' if user.is_staff else 'customer'


def _staff_role_label(role):
    return {
        'commercial': 'بازرگانی',
        'finance': 'مالی',
        'staff': 'کارمندی',
    }.get(role, '')


def _is_staff_user(user):
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    try:
        return user.profile.role in STAFF_ROLES
    except UserProfile.DoesNotExist:
        return False


def _can_upload_invoices(user):
    if user.is_superuser:
        return True
    try:
        return user.profile.can_upload_invoices
    except UserProfile.DoesNotExist:
        return False


def _can_view_invoices(user):
    if user.is_superuser:
        return True
    try:
        return user.profile.can_view_invoices
    except UserProfile.DoesNotExist:
        return False


def _can_manage_users(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def _can_access_payment(user, payment):
    return _is_staff_user(user) or payment.user_id == user.id


def _can_access_invoice(user, invoice):
    if _is_staff_user(user):
        return _can_view_invoices(user)
    return invoice.customer_id == user.id


def _safe_next_url(request, default=''):
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return default


def _file_response(field_file, as_attachment=False):
    if not field_file:
        raise Http404
    try:
        field_file.open('rb')
    except FileNotFoundError as exc:
        raise Http404 from exc
    content_type, _ = mimetypes.guess_type(field_file.name)
    return FileResponse(
        field_file,
        as_attachment=as_attachment,
        filename=field_file.name.rsplit('/', 1)[-1],
        content_type=content_type or 'application/octet-stream',
    )


@require_POST
def safe_logout(request):
    try:
        auth_logout(request)
        return redirect(settings.LOGOUT_REDIRECT_URL)
    except Exception:
        logger.exception('Logout failed; clearing client cookies as a fallback.')
        response = redirect(settings.LOGOUT_REDIRECT_URL)
        response.delete_cookie(
            settings.SESSION_COOKIE_NAME,
            path=settings.SESSION_COOKIE_PATH,
            domain=settings.SESSION_COOKIE_DOMAIN,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )
        response.delete_cookie(
            settings.CSRF_COOKIE_NAME,
            path=settings.CSRF_COOKIE_PATH,
            domain=settings.CSRF_COOKIE_DOMAIN,
            samesite=settings.CSRF_COOKIE_SAMESITE,
        )
        return response


class SafeLoginView(LoginView):
    template_name = 'registration/login.html'

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except DatabaseError:
            logger.exception('Login failed because the session/database could not be written.')
            form.add_error(
                None,
                'ورود انجام نشد، چون سامانه در حال حاضر امکان ثبت نشست کاربر در دیتابیس را ندارد. لطفا با مدیر سیستم تماس بگیرید.',
            )
            return self.form_invalid(form)


def _suggest_five_digit_password():
    lower = 'abcdefghijklmnopqrstuvwxyz'
    upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    digits = '0123456789'
    all_chars = lower + upper + digits

    categories = [lower, upper, digits]
    selected = []
    # ensure at least two categories are represented
    chosen_categories = random.sample(categories, 2)
    for category in chosen_categories:
        selected.append(random.choice(category))
    while len(selected) < 5:
        selected.append(random.choice(all_chars))
    random.shuffle(selected)
    return ''.join(selected)


def _staff_status_choices_for_role(role):
    if role == 'commercial':
        return [
            (PaymentRecord.STATUS_COMMERCIAL_REVIEW, 'تایید بازرگانی'),
            (PaymentRecord.STATUS_INCOMPLETE, 'ناقص'),
            (PaymentRecord.STATUS_REJECTED, 'رد شده'),
        ]
    if role == 'finance':
        return [
            (PaymentRecord.STATUS_FINANCE_REVIEW, 'تایید مالی'),
            (PaymentRecord.STATUS_FINAL_APPROVED, 'تایید نهایی'),
            (PaymentRecord.STATUS_INCOMPLETE, 'ناقص'),
            (PaymentRecord.STATUS_REJECTED, 'رد شده'),
            (PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL, 'عودت به بازرگانی'),
        ]
    return PaymentRecord.STATUS_CHOICES


def _can_staff_act_on_payment(role, payment, is_system_admin=False):
    if is_system_admin:
        return True
    if payment.locked_by_finance:
        return False
    if role == 'commercial':
        return payment.status in {PaymentRecord.STATUS_PENDING, PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL}
    if role == 'finance':
        return True
    return True


def _records_for_user(user):
    qs = PaymentRecord.objects.select_related('counterparty', 'user').prefetch_related('receipts', 'activity_logs')
    if _is_staff_user(user):
        return qs.order_by('-id')
    return qs.filter(user=user).order_by('-id')


def _parse_jalali_date(date_text):
    if not date_text:
        return None
    try:
        return jdatetime.datetime.strptime(date_text, '%Y/%m/%d').date()
    except ValueError:
        return None


def _today_jalali_date():
    return jdatetime.date.fromgregorian(date=timezone.localdate())


def _format_jalali_date(value):
    if not value:
        return ''
    return value.strftime('%Y/%m/%d')


def _format_jalali_datetime(value, date_format='%Y/%m/%d %H:%M'):
    if not value:
        return ''
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return jdatetime.datetime.fromgregorian(datetime=value).strftime(date_format)


def _build_query_string(request, remove_keys=None):
    query_params = request.GET.copy()
    for key in remove_keys or []:
        query_params.pop(key, None)
    return query_params.urlencode()


def _paginate_queryset(request, queryset, per_page=15, page_param='page'):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get(page_param) or 1
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)
    return page_obj


def _excel_response(filename, sheets):
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb = Workbook()
    first = True
    for title, headers, rows in sheets:
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = title[:31]
        ws.append(headers)
        for row in rows:
            ws.append(row)
    wb.save(response)
    return response


def _customer_list_rows(request):
    customers = UserProfile.objects.filter(role='customer').select_related('user').order_by('user__username')
    filters = {
        'q': (request.GET.get('q') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
    }
    if filters['q']:
        customers = customers.filter(
            Q(user__username__icontains=filters['q']) |
            Q(user__first_name__icontains=filters['q']) |
            Q(user__last_name__icontains=filters['q']) |
            Q(first_name__icontains=filters['q']) |
            Q(last_name__icontains=filters['q']) |
            Q(organization__icontains=filters['q']) |
            Q(city__icontains=filters['q']) |
            Q(province__icontains=filters['q']) |
            Q(phone__icontains=filters['q']) |
            Q(mobile__icontains=filters['q'])
        )
    if filters['status'] == 'active':
        customers = customers.filter(suspended=False, user__is_active=True)
    elif filters['status'] == 'suspended':
        customers = customers.filter(suspended=True)
    elif filters['status'] == 'inactive':
        customers = customers.filter(user__is_active=False)

    payment_stats = {
        row['user']: row
        for row in (
            PaymentRecord.objects
            .filter(user__profile__role='customer')
            .values('user')
            .annotate(payment_count=Count('id'), total_amount=Sum('amount'), latest_payment_date=Max('created_at'))
        )
    }
    confirmed_payment_totals = {
        row['user']: row['total'] or 0
        for row in (
            PaymentRecord.objects
            .filter(user__profile__role='customer', status__in=[PaymentRecord.STATUS_APPROVED, PaymentRecord.STATUS_FINAL_APPROVED])
            .values('user')
            .annotate(total=Sum('amount'))
        )
    }
    review_payment_totals = {
        row['user']: row['total'] or 0
        for row in (
            PaymentRecord.objects
            .filter(user__profile__role='customer')
            .exclude(status=PaymentRecord.STATUS_REJECTED)
            .values('user')
            .annotate(total=Sum('amount'))
        )
    }
    invoice_counts = {
        row['customer']: row['invoice_count']
        for row in InvoiceRecord.objects.filter(customer__profile__role='customer').values('customer').annotate(invoice_count=Count('id'))
    }
    invoice_totals = {
        row['customer']: row['total'] or 0
        for row in InvoiceRecord.objects.filter(customer__profile__role='customer').values('customer').annotate(total=Sum('amount'))
    }

    customer_data = []
    for profile in customers:
        stats = payment_stats.get(profile.user_id, {})
        invoice_total = invoice_totals.get(profile.user_id, 0)
        confirmed_payment_total = confirmed_payment_totals.get(profile.user_id, 0)
        review_payment_total = review_payment_totals.get(profile.user_id, 0)
        customer_data.append({
            'profile': profile,
            'user': profile.user,
            'payment_count': stats.get('payment_count') or 0,
            'invoice_count': invoice_counts.get(profile.user_id, 0),
            'total_amount': stats.get('total_amount') or 0,
            'invoice_total': invoice_total,
            'confirmed_debt': invoice_total - confirmed_payment_total,
            'review_debt': invoice_total - review_payment_total,
            'latest_payment_date': stats.get('latest_payment_date'),
        })
    return customer_data, filters


def _log_activity(payment, actor, action, from_status='', to_status='', note=''):
    PaymentActivityLog.objects.create(
        payment=payment,
        actor=actor if actor and actor.is_authenticated else None,
        action=action,
        from_status=from_status or '',
        to_status=to_status or '',
        note=note or '',
    )


def _role_title(user):
    if not user:
        return 'کاربر'
    try:
        role = user.profile.role
    except UserProfile.DoesNotExist:
        role = ''
    return {
        'commercial': 'کاربر بازرگانی',
        'finance': 'کاربر مالی',
        'staff': 'کاربر کارمند',
        'customer': 'مشتری',
    }.get(role, 'کاربر')


def _display_name(user):
    if not user:
        return 'سیستم'
    full_name = f"{user.first_name} {user.last_name}".strip()
    return full_name or user.username


def _log_text(log):
    actor = _display_name(log.actor)
    role = _role_title(log.actor)
    if log.action == PaymentActivityLog.ACTION_VIEWED:
        return f"{role} ({actor}) سند را مشاهده کرد."
    if log.action == PaymentActivityLog.ACTION_CREATED:
        return f"{role} ({actor}) سند را بارگذاری کرد."
    if log.action == PaymentActivityLog.ACTION_EDITED:
        return f"{role} ({actor}) سند را ویرایش کرد."
    if log.action == PaymentActivityLog.ACTION_STATUS_CHANGED:
        status_labels = dict(PaymentRecord.STATUS_CHOICES)
        status_text = status_labels.get(log.to_status, log.to_status)
        return f"{role} ({actor}) وضعیت سند را به «{status_text}» تغییر داد."
    return f"{role} ({actor}) عملیاتی انجام داد."


def _enrich_records(records, staff_role='', is_system_admin=False):
    status_order = [
        PaymentRecord.STATUS_COMMERCIAL_REVIEW,
        PaymentRecord.STATUS_FINANCE_REVIEW,
        PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL,
        PaymentRecord.STATUS_APPROVED,
        PaymentRecord.STATUS_FINAL_APPROVED,
        PaymentRecord.STATUS_REJECTED,
        PaymentRecord.STATUS_INCOMPLETE,
    ]
    records = list(records)
    for payment in records:
        reached = set()
        for log in payment.activity_logs.all():
            if log.to_status in STATUS_FLAG_META:
                reached.add(log.to_status)
        if payment.status in STATUS_FLAG_META:
            reached.add(payment.status)
            for step in STATUS_PROGRESS_FLOWS.get(payment.status, []):
                reached.add(step)

        payment.row_flags = [
            {
                'label': STATUS_FLAG_META[code][0],
                'css': STATUS_FLAG_META[code][1],
            }
            for code in status_order
            if code in reached
        ]
        payment.timeline_lines = [
            {
                'time': _format_jalali_datetime(log.created_at),
                'text': _log_text(log),
                'note': log.note,
            }
            for log in payment.activity_logs.all()[:5]
        ]
        payment.staff_can_act = _can_staff_act_on_payment(
            staff_role,
            payment,
            is_system_admin=is_system_admin,
        ) if staff_role else False
        payment.staff_allowed_choices = _staff_status_choices_for_role(staff_role) if staff_role else []
    return records


def _apply_record_filters(records, request, is_staff_user):
    filters = {
        'first_name': (request.GET.get('first_name') or '').strip(),
        'last_name': (request.GET.get('last_name') or '').strip(),
        'phone': (request.GET.get('phone') or '').strip(),
        'city': (request.GET.get('city') or '').strip(),
        'tracking_code': (request.GET.get('tracking_code') or '').strip(),
        'payer_account_number': (request.GET.get('payer_account_number') or '').strip(),
        'payer_full_name': (request.GET.get('payer_full_name') or '').strip(),
        'payer_bank_name': (request.GET.get('payer_bank_name') or '').strip(),
        'amount': (request.GET.get('amount') or '').replace(',', '').strip(),
        'pay_date': (request.GET.get('pay_date') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
        'counterparty': (request.GET.get('counterparty') or '').strip(),
    }

    if is_staff_user:
        if filters['first_name']:
            records = records.filter(first_name__icontains=filters['first_name'])
        if filters['last_name']:
            records = records.filter(last_name__icontains=filters['last_name'])
        if filters['phone']:
            records = records.filter(phone__icontains=filters['phone'])
        if filters['city']:
            records = records.filter(city__icontains=filters['city'])
        if filters['tracking_code']:
            records = records.filter(tracking_code__icontains=filters['tracking_code'])
        if filters['payer_account_number']:
            records = records.filter(payer_account_number__icontains=filters['payer_account_number'])
        if filters['payer_full_name']:
            records = records.filter(payer_full_name__icontains=filters['payer_full_name'])
        if filters['payer_bank_name']:
            records = records.filter(payer_bank_name__icontains=filters['payer_bank_name'])
        if filters['counterparty'].isdigit():
            records = records.filter(counterparty_id=int(filters['counterparty']))
    else:
        if filters['payer_full_name']:
            records = records.filter(payer_full_name__icontains=filters['payer_full_name'])
        if filters['payer_account_number']:
            records = records.filter(payer_account_number__icontains=filters['payer_account_number'])
        if filters['payer_bank_name']:
            records = records.filter(payer_bank_name__icontains=filters['payer_bank_name'])

    if filters['amount'].isdigit():
        parsed_amount = int(filters['amount'])
        records = records.filter(amount=parsed_amount)
        filters['amount'] = _format_thousand_separator(parsed_amount)

    parsed_date = _parse_jalali_date(filters['pay_date'])
    if parsed_date:
        records = records.filter(pay_date=parsed_date)

    valid_statuses = {choice[0] for choice in PaymentRecord.STATUS_CHOICES}
    if is_staff_user:
        if filters['status'] in valid_statuses:
            records = records.filter(status=filters['status'])
    else:
        customer_status_map = {
            PaymentRecord.STATUS_PENDING: [
                PaymentRecord.STATUS_PENDING,
                PaymentRecord.STATUS_COMMERCIAL_REVIEW,
                PaymentRecord.STATUS_FINANCE_REVIEW,
                PaymentRecord.STATUS_RETURNED_TO_COMMERCIAL,
            ],
            PaymentRecord.STATUS_FINAL_APPROVED: [
                PaymentRecord.STATUS_APPROVED,
                PaymentRecord.STATUS_FINAL_APPROVED,
            ],
            PaymentRecord.STATUS_REJECTED: [PaymentRecord.STATUS_REJECTED],
            PaymentRecord.STATUS_INCOMPLETE: [PaymentRecord.STATUS_INCOMPLETE],
        }
        if filters['status'] in customer_status_map:
            records = records.filter(status__in=customer_status_map[filters['status']])

    return records, filters

def _format_thousand_separator(value):
    try:
        return '{:,}'.format(int(str(value).replace(',', '').strip()))
    except (ValueError, TypeError):
        return value


def _apply_record_sort(records, request):
    sortable_fields = {
        'payer_full_name': 'payer_full_name',
        'pay_date': 'pay_date',
        'tracking_code': 'tracking_code',
        'amount': 'amount',
        'payer_bank_name': 'payer_bank_name',
        'status': 'status',
    }
    current_sort = (request.GET.get('sort') or '').strip()
    current_dir = (request.GET.get('dir') or 'desc').strip().lower()
    if current_dir not in {'asc', 'desc'}:
        current_dir = 'desc'

    sort_field = sortable_fields.get(current_sort)
    if sort_field:
        prefix = '' if current_dir == 'asc' else '-'
        records = records.order_by(f'{prefix}{sort_field}', '-id')
    else:
        records = records.order_by('-id')
        current_sort = ''
        current_dir = 'desc'

    query_params = request.GET.copy()
    query_params.pop('sort', None)
    query_params.pop('dir', None)
    base_query = urlencode(query_params, doseq=True)

    return records, current_sort, current_dir, base_query

def _account_initial_data(user, profile, payment=None):
    payment = payment or PaymentRecord()
    return {
        'first_name': user.first_name or payment.first_name,
        'last_name': user.last_name or payment.last_name,
        'organization': (profile.organization if profile else '') or payment.organization,
        'city': (profile.city if profile else '') or payment.city,
        'phone': (profile.phone if profile else '') or payment.phone,
    }


def _save_receipts(payment, form):
    payload = form.receipt_payload()
    if not payload:
        return

    receipts = [
        PaymentReceipt(payment=payment, image=uploaded, file_hash=file_hash)
        for uploaded, file_hash in payload
    ]
    PaymentReceipt.objects.bulk_create(receipts)


def _source_profiles_for_user(user):
    if not user or not user.is_authenticated:
        return []
    records = (
        PaymentRecord.objects
        .filter(user=user)
        .values(
            'payer_account_number',
            'payer_full_name',
            'payer_bank_name',
        )
        .order_by('-id')
    )
    seen = set()
    profiles = []
    for row in records:
        values = {
            'payer_account_number': (row.get('payer_account_number') or '').strip(),
            'payer_full_name': (row.get('payer_full_name') or '').strip(),
            'payer_bank_name': (row.get('payer_bank_name') or '').strip(),
        }
        if not all(values.values()):
            continue
        if 'Z' in values.values():
            continue
        key = tuple(values[field] for field in (
            'payer_account_number',
            'payer_full_name',
            'payer_bank_name',
        ))
        if key in seen:
            continue
        seen.add(key)
        profiles.append(values)
    return profiles


def _destination_profiles_for_user(user):
    if not user or not user.is_authenticated:
        return []
    records = (
        PaymentRecord.objects
        .filter(user=user)
        .values(
            'beneficiary_bank_name',
            'beneficiary_account_number',
            'beneficiary_account_owner',
        )
        .order_by('-id')
    )
    seen = set()
    profiles = []
    for row in records:
        values = {
            'beneficiary_bank_name': (row.get('beneficiary_bank_name') or '').strip(),
            'beneficiary_account_number': (row.get('beneficiary_account_number') or '').strip(),
            'beneficiary_account_owner': (row.get('beneficiary_account_owner') or '').strip(),
        }
        if not all(values.values()):
            continue
        if 'Z' in values.values():
            continue
        key = tuple(values[field] for field in (
            'beneficiary_bank_name',
            'beneficiary_account_number',
            'beneficiary_account_owner',
        ))
        if key in seen:
            continue
        seen.add(key)
        profiles.append(values)
    return profiles


def _invoice_records_for_user(user):
    qs = InvoiceRecord.objects.select_related('customer', 'customer__profile', 'uploaded_by')
    if _is_staff_user(user):
        # Staff can see all invoices only if they have permission
        if not _can_view_invoices(user):
            return InvoiceRecord.objects.none()
        return qs.order_by('-created_at', '-id')
    # Customers can always see their own invoices
    return qs.filter(customer=user).order_by('-created_at', '-id')


def _invoice_customer_rows():
    rows = []
    profiles = UserProfile.objects.filter(role='customer').select_related('user').order_by(
        'user__first_name', 'user__last_name', 'user__username'
    )
    for profile in profiles:
        full_name = profile.user.get_full_name().strip() or profile.user.username
        rows.append({
            'profile_id': profile.id,
            'user_id': profile.user_id,
            'full_name': full_name,
            'username': profile.user.username,
            'organization': profile.organization or '-',
            'city': profile.city or '-',
            'phone': profile.phone or '-',
            'search_blob': ' '.join(
                filter(None, [full_name, profile.user.username, profile.organization, profile.city, profile.phone])
            ).lower(),
        })
    return rows


def _customer_debt_summary(user):
    invoice_total = InvoiceRecord.objects.filter(customer=user).aggregate(total=Sum('amount'))['total'] or 0
    confirmed_payment_total = PaymentRecord.objects.filter(
        user=user,
        status__in=[
            PaymentRecord.STATUS_APPROVED,
            PaymentRecord.STATUS_FINAL_APPROVED,
        ],
    ).aggregate(total=Sum('amount'))['total'] or 0
    review_payment_total = PaymentRecord.objects.filter(user=user).exclude(
        status=PaymentRecord.STATUS_REJECTED,
    ).aggregate(total=Sum('amount'))['total'] or 0

    return {
        'invoice_total': invoice_total,
        'confirmed_payment_total': confirmed_payment_total,
        'review_payment_total': review_payment_total,
        'confirmed_debt': invoice_total - confirmed_payment_total,
        'review_debt': invoice_total - review_payment_total,
        'pending_review_payment_total': review_payment_total - confirmed_payment_total,
    }


def _can_manage_daily_payments(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _user_role(user) in {'staff', 'commercial'}


def _can_view_daily_payments(user):
    return _is_staff_user(user)


def _active_daily_assignment_for_user(user):
    if not user or not user.is_authenticated:
        return None
    today = _today_jalali_date()
    return (
        DailyPaymentAssignment.objects
        .select_related('plan', 'customer')
        .filter(customer=user, plan__deposit_date=today)
        .order_by('-id')
        .first()
    )


def _latest_expired_daily_assignment_for_user(user):
    if not user or not user.is_authenticated:
        return None
    today = _today_jalali_date()
    return (
        DailyPaymentAssignment.objects
        .select_related('plan', 'customer')
        .filter(customer=user, plan__deposit_date__lt=today)
        .order_by('-plan__deposit_date', '-id')
        .first()
    )


def _daily_assignment_stats(assignments):
    assignment_ids = [assignment.id for assignment in assignments]
    if not assignment_ids:
        return {}

    paid_rows = (
        PaymentRecord.objects
        .filter(daily_assignment_id__in=assignment_ids)
        .exclude(status=PaymentRecord.STATUS_REJECTED)
        .values('daily_assignment')
        .annotate(total=Sum('amount'), count=Count('id'))
    )
    confirmed_rows = (
        PaymentRecord.objects
        .filter(
            daily_assignment_id__in=assignment_ids,
            status__in=[
                PaymentRecord.STATUS_APPROVED,
                PaymentRecord.STATUS_FINAL_APPROVED,
            ],
        )
        .values('daily_assignment')
        .annotate(total=Sum('amount'), count=Count('id'))
    )
    stats = {
        assignment_id: {
            'paid_amount': 0,
            'payment_count': 0,
            'confirmed_amount': 0,
            'confirmed_count': 0,
        }
        for assignment_id in assignment_ids
    }
    for row in paid_rows:
        data = stats[row['daily_assignment']]
        data['paid_amount'] = row['total'] or 0
        data['payment_count'] = row['count'] or 0
    for row in confirmed_rows:
        data = stats[row['daily_assignment']]
        data['confirmed_amount'] = row['total'] or 0
        data['confirmed_count'] = row['count'] or 0
    return stats


def _managed_users(query='', role='', status=''):
    users = User.objects.select_related('profile').order_by('username')
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(profile__phone__icontains=query) |
            Q(profile__mobile__icontains=query) |
            Q(profile__organization__icontains=query) |
            Q(profile__city__icontains=query) |
            Q(profile__province__icontains=query)
        )
    if role:
        users = users.filter(profile__role=role)
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)
    elif status == 'suspended':
        users = users.filter(profile__suspended=True)
    return users


def _apply_invoice_filters(records, request, is_staff_user):
    filters = {
        'customer': (request.GET.get('customer') or '').strip(),
        'invoice_number': (request.GET.get('invoice_number') or '').strip(),
        'reference_number': (request.GET.get('reference_number') or '').strip(),
        'amount': (request.GET.get('amount') or '').replace(',', '').strip(),
        'invoice_date': (request.GET.get('invoice_date') or '').strip(),
        'seen': (request.GET.get('seen') or '').strip(),
    }

    if is_staff_user and filters['customer']:
        records = records.filter(
            Q(customer__first_name__icontains=filters['customer']) |
            Q(customer__last_name__icontains=filters['customer']) |
            Q(customer__username__icontains=filters['customer']) |
            Q(customer__profile__organization__icontains=filters['customer'])
        )

    if filters['invoice_number']:
        records = records.filter(invoice_number__icontains=filters['invoice_number'])

    if filters['reference_number']:
        records = records.filter(reference_number__icontains=filters['reference_number'])

    if filters['amount'].isdigit():
        parsed_amount = int(filters['amount'])
        records = records.filter(amount=parsed_amount)
        filters['amount'] = _format_thousand_separator(parsed_amount)

    parsed_date = _parse_jalali_date(filters['invoice_date'])
    if parsed_date:
        records = records.filter(invoice_date=parsed_date)

    if filters['seen'] == 'seen':
        records = records.filter(customer_seen_at__isnull=False)
    elif filters['seen'] == 'unseen':
        records = records.filter(customer_seen_at__isnull=True)

    return records, filters


@login_required
def daily_payment_plans(request):
    if not _can_view_daily_payments(request.user):
        return HttpResponseForbidden('این بخش فقط برای کاربران واحدهای شرکت قابل دسترسی است.')

    can_manage = _can_manage_daily_payments(request.user)
    selected_date_text = (request.GET.get('date') or '').strip()
    selected_date = _parse_jalali_date(selected_date_text) or _today_jalali_date()
    previous_date = selected_date - jdatetime.timedelta(days=1)
    next_date = selected_date + jdatetime.timedelta(days=1)

    if request.method == 'POST':
        if not can_manage:
            return HttpResponseForbidden('شما دسترسی ایجاد برنامه واریز روزانه را ندارید.')
        plan_form = DailyPaymentPlanForm(request.POST)
        if plan_form.is_valid():
            plan = plan_form.save(commit=False)
            plan.created_by = request.user
            plan.save()
            messages.success(request, 'برنامه واریز روزانه ثبت شد.')
            detail_url = f"{reverse('daily_payment_plan_detail', kwargs={'plan_id': plan.id})}?{urlencode({'next': request.get_full_path()})}"
            return redirect(detail_url)
    else:
        plan_form = DailyPaymentPlanForm(initial={'deposit_date': _today_jalali_date()})

    plans = list(
        DailyPaymentPlan.objects
        .select_related('created_by')
        .prefetch_related('assignments')
        .filter(deposit_date=selected_date)
        .order_by('-id')
    )
    for plan in plans:
        assignments = list(plan.assignments.all())
        stats = _daily_assignment_stats(assignments)
        plan.assignment_count = len(assignments)
        plan.assigned_expected_total = sum(assignment.expected_amount for assignment in assignments)
        plan.paid_total = sum(stats.get(assignment.id, {}).get('paid_amount', 0) for assignment in assignments)
        plan.confirmed_total = sum(stats.get(assignment.id, {}).get('confirmed_amount', 0) for assignment in assignments)
        plan.remaining_total = plan.assigned_expected_total - plan.paid_total

    return render(request, 'payments/daily_payment_plans.html', {
        'form': plan_form,
        'plans': plans,
        'selected_date': selected_date,
        'selected_date_text': _format_jalali_date(selected_date),
        'previous_date_text': _format_jalali_date(previous_date),
        'next_date_text': _format_jalali_date(next_date),
        'today_date_text': _format_jalali_date(_today_jalali_date()),
        'can_manage_daily_payments': can_manage,
        'user_display_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
    })


@login_required
def daily_payment_plan_detail(request, plan_id):
    if not _can_view_daily_payments(request.user):
        return HttpResponseForbidden('این بخش فقط برای کاربران واحدهای شرکت قابل دسترسی است.')

    plan = get_object_or_404(DailyPaymentPlan.objects.select_related('created_by'), id=plan_id)
    can_manage = _can_manage_daily_payments(request.user)
    return_url = _safe_next_url(request, default=f"{reverse('daily_payment_plans')}?date={_format_jalali_date(plan.deposit_date)}")
    detail_url = f"{request.path}?{urlencode({'next': return_url})}"

    if request.method == 'POST':
        if not can_manage:
            return HttpResponseForbidden('شما دسترسی ویرایش تخصیص واریز روزانه را ندارید.')
        if request.POST.get('action') == 'remove_assignment':
            assignment_id = request.POST.get('assignment_id')
            assignment = get_object_or_404(DailyPaymentAssignment, id=assignment_id, plan=plan)
            assignment.delete()
            messages.success(request, 'تخصیص مشتری حذف شد.')
            return redirect(detail_url)

        assignment_form = DailyPaymentAssignmentForm(request.POST)
        if assignment_form.is_valid():
            assignment = assignment_form.save(commit=False)
            assignment.plan = plan
            try:
                assignment.save()
            except IntegrityError:
                assignment_form.add_error('customer', 'برای این مشتری در این برنامه قبلاً تخصیص ثبت شده است.')
            else:
                messages.success(request, 'تخصیص مشتری ثبت شد.')
                return redirect(detail_url)
    else:
        assignment_form = DailyPaymentAssignmentForm()

    assignments = list(
        plan.assignments
        .select_related('customer', 'customer__profile')
        .prefetch_related('payments', 'payments__receipts')
        .all()
    )
    stats = _daily_assignment_stats(assignments)
    for assignment in assignments:
        assignment.report = stats.get(assignment.id, {
            'paid_amount': 0,
            'payment_count': 0,
            'confirmed_amount': 0,
            'confirmed_count': 0,
        })
        assignment.remaining_amount = assignment.expected_amount - assignment.report['paid_amount']
        assignment.confirmed_remaining_amount = assignment.expected_amount - assignment.report['confirmed_amount']

    totals = {
        'expected': sum(assignment.expected_amount for assignment in assignments),
        'paid': sum(assignment.report['paid_amount'] for assignment in assignments),
        'confirmed': sum(assignment.report['confirmed_amount'] for assignment in assignments),
        'payment_count': sum(assignment.report['payment_count'] for assignment in assignments),
    }
    totals['remaining'] = totals['expected'] - totals['paid']
    totals['confirmed_remaining'] = totals['expected'] - totals['confirmed']

    return render(request, 'payments/daily_payment_plan_detail.html', {
        'plan': plan,
        'assignments': assignments,
        'assignment_form': assignment_form,
        'totals': totals,
        'can_manage_daily_payments': can_manage,
        'user_display_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
        'return_url': return_url,
    })


@login_required
def create_payment(request):
    profile = None
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = None

    initial_data = _account_initial_data(request.user, profile)
    is_staff_user = _is_staff_user(request.user)
    staff_role = _user_role(request.user) if is_staff_user else ''
    is_system_admin = request.user.is_superuser
    active_daily_assignment = _active_daily_assignment_for_user(request.user) if not is_staff_user else None
    expired_daily_assignment = None
    if not is_staff_user and not active_daily_assignment:
        expired_daily_assignment = _latest_expired_daily_assignment_for_user(request.user)
    form_initial = initial_data.copy()
    if active_daily_assignment and request.method != 'POST':
        form_initial.update({
            'beneficiary_bank_name': active_daily_assignment.plan.bank_name,
            'beneficiary_account_number': active_daily_assignment.plan.account_number,
            'beneficiary_account_owner': active_daily_assignment.plan.account_owner,
            'pay_date': active_daily_assignment.plan.deposit_date,
        })

    if request.method == 'POST':
        if is_staff_user:
            return HttpResponseForbidden('کاربران واحدها امکان ثبت سند از این فرم را ندارند.')
        form = PaymentRecordForm(request.POST, request.FILES, initial=form_initial)
        if form.is_valid():
            submitted_account = (form.cleaned_data.get('beneficiary_account_number') or '').replace(' ', '').strip()
            if active_daily_assignment:
                expected_date = active_daily_assignment.plan.deposit_date
                if form.cleaned_data.get('pay_date') != expected_date:
                    form.add_error('pay_date', 'این شماره حساب فقط برای تاریخ اعلام شده امروز معتبر است.')
                expected_account = (active_daily_assignment.plan.account_number or '').replace(' ', '').strip()
                if submitted_account != expected_account:
                    form.add_error('beneficiary_account_number', 'شماره حساب مقصد باید همان شماره حساب اعلام شده امروز باشد.')
            elif submitted_account:
                assigned_accounts = (
                    DailyPaymentAssignment.objects
                    .select_related('plan')
                    .filter(customer=request.user, plan__account_number__iexact=form.cleaned_data.get('beneficiary_account_number'))
                )
                if assigned_accounts.exists():
                    form.add_error('beneficiary_account_number', 'این شماره حساب برای امروز معتبر نیست و امکان ثبت فیش با آن وجود ندارد.')

            if not form.errors:
                payment = form.save(commit=False)
                payment.user = request.user
                payment.first_name = initial_data['first_name']
                payment.last_name = initial_data['last_name']
                payment.organization = initial_data['organization']
                payment.city = initial_data['city']
                payment.phone = initial_data['phone']
                payment.status = PaymentRecord.STATUS_PENDING
                payment.daily_assignment = active_daily_assignment
                payment.save()
                _save_receipts(payment, form)
                _log_activity(payment, request.user, PaymentActivityLog.ACTION_CREATED, to_status=payment.status)
                return redirect('success')
    else:
        form = PaymentRecordForm(initial=form_initial)

    records = _records_for_user(request.user)
    records, active_filters = _apply_record_filters(records, request, is_staff_user)
    records, current_sort, current_sort_dir, sort_base_query = _apply_record_sort(records, request)
    records = _enrich_records(records, staff_role=staff_role, is_system_admin=is_system_admin)
    page_obj = _paginate_queryset(request, records, per_page=15, page_param='page')
    page_base_query = _build_query_string(request, remove_keys=['page'])
    user_display_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

    return render(request, 'payments/form.html', {
        'form': form,
        'records': page_obj,
        'page_obj': page_obj,
        'page_base_query': page_base_query,
        'is_staff_user': is_staff_user,
        'filters': active_filters,
        'status_choices': PaymentRecord.STATUS_CHOICES if is_staff_user else CUSTOMER_STATUSES,
        'counterparties': Counterparty.objects.all() if is_staff_user else [],
        'staff_user_role': staff_role,
        'staff_role_label': _staff_role_label(staff_role),
        'can_manage_counterparties': is_system_admin,
        'can_export_records': (not is_staff_user) or is_system_admin or staff_role in {'finance', 'commercial'},
        'is_system_admin': is_system_admin,
        'user_display_name': user_display_name,
        'source_profiles': _source_profiles_for_user(request.user) if not is_staff_user else [],
        'destination_profiles': _destination_profiles_for_user(request.user) if not is_staff_user else [],
        'current_sort': current_sort,
        'current_sort_dir': current_sort_dir,
        'sort_base_query': sort_base_query,
        'customer_info': initial_data,
        'customer_debt': _customer_debt_summary(request.user) if not is_staff_user else None,
        'active_daily_assignment': active_daily_assignment,
        'expired_daily_assignment': expired_daily_assignment,
    })


@login_required
def success(request):
    records = _records_for_user(request.user)
    return render(request, 'payments/success.html', {'records': records})


@login_required
def profile_password_change(request):
    profile = getattr(request.user, 'profile', None)
    is_force_change = bool(profile and profile.role == 'customer' and profile.force_password_change)
    show_initial_password_change_note = bool(
        is_force_change and request.session.get('show_initial_password_change_note')
    )

    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            if profile and profile.role == 'customer' and profile.force_password_change:
                profile.force_password_change = False
                profile.save(update_fields=['force_password_change'])
            request.session.pop('show_initial_password_change_note', None)
            messages.success(request, 'رمز عبور با موفقیت تغییر کرد.')
            return redirect('submit')
        messages.error(request, 'تغییر رمز انجام نشد. لطفا خطاها را بررسی کنید.')
    else:
        form = CustomPasswordChangeForm(request.user)

    return render(request, 'payments/profile_password_change.html', {
        'form': form,
        'is_force_change': is_force_change,
        'show_initial_password_change_note': show_initial_password_change_note,
        'username': request.user.username,
    })


def _log_system_activity(actor, target_user, action, description=''):
    SystemActivityLog.objects.create(
        actor=actor if actor and actor.is_authenticated else None,
        target_user=target_user,
        action=action,
        description=description,
    )


@login_required
def profile_edit(request):
    profile = get_object_or_404(UserProfile, user=request.user)

    if request.method == 'POST':
        form = CustomerProfileUpdateForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            changes = form.changed_profile_fields()
            form.save()
            if changes:
                change_text = '؛ '.join(
                    f"{item['field']}: از «{item['old']}» به «{item['new']}»"
                    for item in changes
                )
                _log_system_activity(
                    request.user,
                    request.user,
                    SystemActivityLog.ACTION_PROFILE_UPDATED,
                    f'مشخصات کاربر توسط خودش ویرایش شد. {change_text}',
                )
            messages.success(request, 'مشخصات شما با موفقیت ذخیره شد.')
            return redirect('profile_edit')
        messages.error(request, 'ذخیره مشخصات انجام نشد. لطفا خطاها را بررسی کنید.')
    else:
        form = CustomerProfileUpdateForm(instance=profile, user=request.user)

    return render(request, 'payments/profile_edit.html', {
        'form': form,
        'username': request.user.username,
    })


def _send_temporary_password_email(user, temp_password):
    if not user.email:
        return False, 'برای این کاربر ایمیل ثبت نشده است.'

    subject = 'رمز عبور جدید سامانه'
    message = (
        f'{user.get_full_name() or user.username} عزیز،\n\n'
        f'رمز عبور جدید شما در سامانه: {temp_password}\n\n'
        'پس از ورود، لازم است رمز عبور خود را تغییر دهید.'
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
    return True, ''


@login_required
def profile_password_cancel(request):
    profile = getattr(request.user, 'profile', None)
    is_force_change = bool(profile and profile.role == 'customer' and profile.force_password_change)
    request.session.pop('show_initial_password_change_note', None)
    if is_force_change:
        auth_logout(request)
        return redirect('login')
    return redirect('submit')


@login_required
@require_POST
def staff_update_status(request, payment_id):
    redirect_target = _safe_next_url(request, default=request.META.get('HTTP_REFERER') or '')
    if not redirect_target:
        redirect_target = 'submit'

    if not _is_staff_user(request.user):
        messages.error(request, 'شما دسترسی بررسی اسناد را ندارید.')
        return redirect(redirect_target)

    payment = get_object_or_404(PaymentRecord, id=payment_id)
    staff_role = _user_role(request.user)
    if not _can_staff_act_on_payment(staff_role, payment, is_system_admin=request.user.is_superuser):
        messages.error(request, 'در وضعیت فعلی، امکان تغییر این سند برای شما وجود ندارد.')
        return redirect(redirect_target)

    form = StaffStatusUpdateForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'اطلاعات ارسالی معتبر نیست.')
        return redirect(redirect_target)

    target_status = form.cleaned_data['status']
    allowed_statuses = {value for value, _ in _staff_status_choices_for_role(staff_role)}
    if not request.user.is_superuser and target_status not in allowed_statuses:
        messages.error(request, 'این تغییر وضعیت برای نقش شما مجاز نیست.')
        return redirect(redirect_target)

    note = (form.cleaned_data['note'] or '').strip()
    if target_status in {PaymentRecord.STATUS_REJECTED, PaymentRecord.STATUS_INCOMPLETE} and not note:
        messages.error(request, 'برای وضعیت «رد شده» یا «ناقص»، ثبت توضیح الزامی است.')
        return redirect(redirect_target)

    from_status = payment.status
    payment.status = target_status
    payment.last_staff_note = note

    # Finance can hard-lock records on terminal decisions.
    if request.user.is_superuser:
        payment.locked_by_finance = False
    elif staff_role == 'finance' and target_status in {
        PaymentRecord.STATUS_FINAL_APPROVED,
        PaymentRecord.STATUS_REJECTED,
        PaymentRecord.STATUS_INCOMPLETE,
    }:
        payment.locked_by_finance = True

    selected_counterparty = form.cleaned_data['counterparty']
    if selected_counterparty and staff_role in {'commercial', 'staff'}:
        payment.counterparty = selected_counterparty

    payment.save(update_fields=['status', 'last_staff_note', 'counterparty', 'locked_by_finance'])

    _log_activity(
        payment,
        request.user,
        PaymentActivityLog.ACTION_STATUS_CHANGED,
        from_status=from_status,
        to_status=payment.status,
        note=payment.last_staff_note,
    )

    messages.success(request, 'وضعیت سند با موفقیت ثبت شد.')
    return redirect(redirect_target)


@login_required
def edit_payment(request, payment_id):
    payment = get_object_or_404(PaymentRecord, id=payment_id)
    return_url = _safe_next_url(request)

    if _is_staff_user(request.user):
        return HttpResponseForbidden('کاربران واحدها امکان ویرایش سند مشتری را ندارند.')

    if payment.user_id != request.user.id:
        return HttpResponseForbidden('فقط امکان ویرایش اسناد ثبت شده توسط خودتان وجود دارد.')

    if payment.status != PaymentRecord.STATUS_INCOMPLETE:
        return HttpResponseForbidden('فقط اسناد با وضعیت «ناقص» قابل ویرایش هستند.')

    profile = None
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = None

    initial_data = _account_initial_data(request.user, profile, payment=payment)

    if request.method == 'POST':
        form = PaymentRecordForm(request.POST, request.FILES, instance=payment, initial=initial_data)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.user = request.user
            payment.first_name = initial_data['first_name']
            payment.last_name = initial_data['last_name']
            payment.organization = initial_data['organization']
            payment.city = initial_data['city']
            payment.phone = initial_data['phone']
            from_status = payment.status
            payment.status = PaymentRecord.STATUS_PENDING
            payment.locked_by_finance = False
            payment.save()
            _save_receipts(payment, form)
            _log_activity(payment, request.user, PaymentActivityLog.ACTION_EDITED, from_status=from_status, to_status=payment.status)
            return redirect(return_url or 'submit')
    else:
        form = PaymentRecordForm(instance=payment, initial=initial_data)

    return render(request, 'payments/edit_payment.html', {
        'form': form,
        'payment': payment,
        'source_profiles': _source_profiles_for_user(request.user),
        'destination_profiles': _destination_profiles_for_user(request.user),
        'customer_info': initial_data,
        'customer_debt': _customer_debt_summary(request.user),
        'return_url': return_url,
    })


@login_required
def payment_timeline(request, payment_id):
    payment = get_object_or_404(PaymentRecord.objects.select_related('user', 'counterparty'), id=payment_id)
    if not _is_staff_user(request.user) and payment.user_id != request.user.id:
        return HttpResponseForbidden('فقط امکان مشاهده تاریخچه اسناد خودتان وجود دارد.')

    _log_activity(payment, request.user, PaymentActivityLog.ACTION_VIEWED, note='مشاهده تاریخچه')
    raw_logs = payment.activity_logs.select_related('actor').all()
    logs = [
        {
            'log': log,
            'jalali_time': _format_jalali_datetime(log.created_at),
        }
        for log in raw_logs
    ]

    return render(request, 'payments/timeline.html', {
        'payment': payment,
        'logs': logs,
        'is_staff_user': _is_staff_user(request.user),
        'return_url': _safe_next_url(request),
    })


@login_required
def counterparties_manage(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('شما دسترسی مدیریت طرف حساب را ندارید.')

    if request.method == 'POST':
        form = CounterpartyForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('counterparties_manage')
    else:
        form = CounterpartyForm()

    counterparties = Counterparty.objects.all()
    page_obj = _paginate_queryset(request, counterparties, per_page=15, page_param='page')
    page_base_query = _build_query_string(request, remove_keys=['page'])
    return render(request, 'payments/counterparties.html', {
        'form': form,
        'counterparties': page_obj,
        'page_obj': page_obj,
        'page_base_query': page_base_query,
    })


@login_required
def counterparty_edit(request, counterparty_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden('شما دسترسی مدیریت طرف حساب را ندارید.')

    counterparty = get_object_or_404(Counterparty, id=counterparty_id)

    if request.method == 'POST':
        form = CounterpartyForm(request.POST, instance=counterparty)
        if form.is_valid():
            form.save()
            return redirect('counterparties_manage')
    else:
        form = CounterpartyForm(instance=counterparty)

    return render(request, 'payments/counterparty_edit.html', {'form': form, 'counterparty': counterparty})


@login_required
def users_manage(request):
    if not _can_manage_users(request.user):
        return HttpResponseForbidden('شما دسترسی مدیریت کاربران را ندارید.')

    password_suggestion = _suggest_five_digit_password()
    filters = {
        'q': (request.GET.get('q') or '').strip(),
        'role': (request.GET.get('role') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
    }
    if request.method == 'POST':
        form = UserAccountManagementForm(request.POST, password_suggestion=password_suggestion)
        if form.is_valid():
            created_user = form.save()
            _log_system_activity(
                request.user,
                created_user,
                SystemActivityLog.ACTION_USER_CREATED,
                'کاربر جدید ایجاد شد.',
            )
            messages.success(request, 'کاربر جدید با موفقیت ایجاد شد.')
            return redirect('users_manage')
    else:
        form = UserAccountManagementForm(
            initial={'password': password_suggestion, 'force_password_change': True, 'is_active': True},
            password_suggestion=password_suggestion,
        )

    users_page = _paginate_queryset(
        request,
        _managed_users(query=filters['q'], role=filters['role'], status=filters['status']),
        per_page=15,
        page_param='page',
    )
    page_base_query = _build_query_string(request, remove_keys=['page'])
    return render(request, 'payments/users_manage.html', {
        'form': form,
        'users': users_page,
        'page_obj': users_page,
        'page_base_query': page_base_query,
        'password_suggestion': password_suggestion,
        'editing_user': None,
        'filters': filters,
    })


@login_required
def user_edit(request, user_id):
    if not _can_manage_users(request.user):
        return HttpResponseForbidden('شما دسترسی مدیریت کاربران را ندارید.')

    managed_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)
    password_suggestion = _suggest_five_digit_password()
    filters = {
        'q': (request.GET.get('q') or '').strip(),
        'role': (request.GET.get('role') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
    }

    if request.method == 'POST':
        form = UserAccountManagementForm(
            request.POST,
            instance=managed_user,
            password_suggestion=password_suggestion,
        )
        if form.is_valid():
            form.save()
            _log_system_activity(
                request.user,
                managed_user,
                SystemActivityLog.ACTION_USER_UPDATED,
                'اطلاعات کاربر ویرایش شد.',
            )
            messages.success(request, 'اطلاعات کاربر با موفقیت بروزرسانی شد.')
            return redirect('users_manage')
    else:
        form = UserAccountManagementForm(instance=managed_user, password_suggestion=password_suggestion)

    users_page = _paginate_queryset(
        request,
        _managed_users(query=filters['q'], role=filters['role'], status=filters['status']),
        per_page=15,
        page_param='page',
    )
    page_base_query = _build_query_string(request, remove_keys=['page'])
    return render(request, 'payments/users_manage.html', {
        'form': form,
        'users': users_page,
        'page_obj': users_page,
        'page_base_query': page_base_query,
        'password_suggestion': password_suggestion,
        'editing_user': managed_user,
        'filters': filters,
    })


@login_required
def invoices_dashboard(request):
    is_staff_user = _is_staff_user(request.user)
    can_upload_invoices = _can_upload_invoices(request.user)

    if request.method == 'POST':
        if not can_upload_invoices:
            return HttpResponseForbidden('شما دسترسی بارگذاری فاکتور مشتری را ندارید.')
        form = InvoiceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.uploaded_by = request.user
            # مقدار amount را تنظیم کنیم
            invoice.amount = form.cleaned_data.get('amount')
            invoice.save()
            messages.success(request, 'فاکتور با موفقیت برای مشتری ثبت شد.')
            return redirect('invoices_dashboard')
    else:
        form = InvoiceUploadForm()

    can_view_invoices = _can_view_invoices(request.user)
    records = _invoice_records_for_user(request.user)
    records, filters = _apply_invoice_filters(records, request, is_staff_user=is_staff_user)
    page_obj = _paginate_queryset(request, records, per_page=15, page_param='page')
    page_base_query = _build_query_string(request, remove_keys=['page'])
    user_display_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

    return render(request, 'payments/invoices.html', {
        'form': form,
        'records': page_obj,
        'page_obj': page_obj,
        'page_base_query': page_base_query,
        'filters': filters,
        'is_staff_user': is_staff_user,
        'can_upload_invoices': can_upload_invoices,
        'can_view_invoices': can_view_invoices,
        'user_display_name': user_display_name,
        'customer_rows': _invoice_customer_rows() if can_upload_invoices else [],
    })


@login_required
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(
        InvoiceRecord.objects.select_related('customer', 'customer__profile', 'uploaded_by'),
        id=invoice_id,
    )
    is_staff_user = _is_staff_user(request.user)
    just_marked_seen = False
    return_url = _safe_next_url(request)

    # Staff needs permission to view invoices
    if is_staff_user and not _can_view_invoices(request.user):
        return HttpResponseForbidden('شما دسترسی مشاهده فاکتور را ندارید.')

    # Customers can only see their own invoices
    if not is_staff_user and invoice.customer_id != request.user.id:
        return HttpResponseForbidden('فقط امکان مشاهده فاکتورهای خودتان وجود دارد.')

    if not is_staff_user and invoice.customer_seen_at is None:
        invoice.customer_seen_at = timezone.now()
        invoice.save(update_fields=['customer_seen_at'])
        just_marked_seen = True

    if request.method == 'POST':
        if is_staff_user:
            return HttpResponseForbidden('ثبت یادداشت فقط برای مشتری فعال است.')
        form = InvoiceCustomerNoteForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, 'یادداشت شما ذخیره شد.')
            redirect_url = request.path
            if return_url:
                redirect_url = f"{redirect_url}?{urlencode({'next': return_url})}"
            return redirect(redirect_url)
    else:
        form = InvoiceCustomerNoteForm(instance=invoice)

    customer_profile = getattr(invoice.customer, 'profile', None)
    return render(request, 'payments/invoice_detail.html', {
        'invoice': invoice,
        'form': form,
        'is_staff_user': is_staff_user,
        'customer_profile': customer_profile,
        'just_marked_seen': just_marked_seen,
        'return_url': return_url,
    })


@login_required
def invoice_file(request, invoice_id):
    invoice = get_object_or_404(InvoiceRecord, id=invoice_id)
    if not _can_access_invoice(request.user, invoice):
        return HttpResponseForbidden('فقط امکان مشاهده فایل فاکتورهای خودتان وجود دارد.')
    return _file_response(invoice.attachment, as_attachment=request.GET.get('download') == '1')


@login_required
def receipt_file(request, receipt_id):
    receipt = get_object_or_404(PaymentReceipt.objects.select_related('payment'), id=receipt_id)
    if not _can_access_payment(request.user, receipt.payment):
        return HttpResponseForbidden('فقط امکان مشاهده فایل فیش‌های خودتان وجود دارد.')
    return _file_response(receipt.image)


@login_required
def legacy_payment_receipt_file(request, payment_id):
    payment = get_object_or_404(PaymentRecord, id=payment_id)
    if not _can_access_payment(request.user, payment):
        return HttpResponseForbidden('فقط امکان مشاهده فایل فیش‌های خودتان وجود دارد.')
    return _file_response(payment.receipt_image)


def login_ad_image(request, ad_id):
    ad = get_object_or_404(LoginAdvertisement, id=ad_id, is_visible=True)
    today = timezone.localdate()
    if ad.start_date > today or ad.end_date < today:
        raise Http404
    return _file_response(ad.image)


@login_required
def bank_names_autocomplete(request):
    """
    API endpoint for bank names autocomplete.
    Returns list of unique bank names matching the search query.
    """
    query = (request.GET.get('q') or '').strip()
    field_type = (request.GET.get('type') or 'payer').strip()  # 'payer' or 'beneficiary'
    
    if len(query) < 1:
        return JsonResponse({'results': []})
    
    if field_type == 'beneficiary':
        bank_names = (
            PaymentRecord.objects
            .filter(beneficiary_bank_name__icontains=query)
            .values_list('beneficiary_bank_name', flat=True)
            .distinct()
            .order_by('beneficiary_bank_name')[:20]
        )
    else:  # payer
        bank_names = (
            PaymentRecord.objects
            .filter(payer_bank_name__icontains=query)
            .values_list('payer_bank_name', flat=True)
            .distinct()
            .order_by('payer_bank_name')[:20]
        )
    
    results = [{'text': name, 'id': name} for name in bank_names if name]
    return JsonResponse({'results': results})


@login_required
def export_records(request):
    is_staff_user = _is_staff_user(request.user)
    role = _user_role(request.user)
    if is_staff_user and not request.user.is_superuser and role not in {'finance', 'commercial'}:
        return HttpResponseForbidden('خروجی برای نقش کاربری شما فعال نیست.')

    records = _records_for_user(request.user)
    records, _ = _apply_record_filters(records, request, is_staff_user=is_staff_user)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="payment_records.xlsx"'

    wb = Workbook()
    ws = wb.active
    ws.title = 'Payments'

    ws.append([
        'ID',
        'کاربر',
        'نام کاربر',
        'نام',
        'نام خانوادگی',
        'نام و نام خانوادگی واریز کننده',
        'شماره حساب واریز کننده',
        'نام بانک',
        'نام بانک مقصد',
        'شماره حساب مقصد',
        'نام صاحب حساب مقصد',
        'مجموعه',
        'شهر',
        'شماره تلفن',
        'مبلغ (ریال)',
        'تاریخ واریز',
        'کد پیگیری',
        'طرف حساب',
        'تاریخ ثبت',
    ])

    for payment in records:
        ws.append([
            payment.id,
            payment.user.get_full_name() if payment.user else '',
            payment.user.username if payment.user else '',
            payment.first_name,
            payment.last_name,
            payment.payer_full_name,
            payment.payer_account_number,
            payment.payer_bank_name,
            payment.beneficiary_bank_name,
            payment.beneficiary_account_number,
            payment.beneficiary_account_owner,
            payment.organization,
            payment.city,
            payment.phone,
            payment.amount,
            str(payment.pay_date),
            payment.tracking_code or '',
            payment.counterparty.name if payment.counterparty else '',
            _format_jalali_datetime(payment.created_at),
        ])

    wb.save(response)
    return response


@login_required
def customer_detail(request, user_id):
    """
    Dedicated view for staff to see all documents (payments and invoices) for a specific customer.
    """
    is_staff_user = _is_staff_user(request.user)
    if not is_staff_user:
        return HttpResponseForbidden('این بخش فقط برای کاربران واحدها قابل دسترسی است.')
    return_url = _safe_next_url(request)

    # Get the customer user
    customer_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)
    customer_profile = getattr(customer_user, 'profile', None)

    # Get all payments for this customer
    payments = (
        PaymentRecord.objects
        .filter(user=customer_user)
        .select_related('counterparty', 'user')
        .prefetch_related('receipts', 'activity_logs', 'activity_logs__actor')
        .order_by('-created_at')
    )
    payments = _enrich_records(payments, staff_role=_user_role(request.user), is_system_admin=request.user.is_superuser)

    # Get all invoices for this customer
    invoices = (
        InvoiceRecord.objects
        .filter(customer=customer_user)
        .select_related('customer', 'customer__profile', 'uploaded_by')
        .order_by('-created_at')
    )
    can_view_invoices = _can_view_invoices(request.user)
    if not can_view_invoices:
        invoices = InvoiceRecord.objects.none()

    invoice_number_filter = (request.GET.get('invoice_number') or '').strip()
    if invoice_number_filter and can_view_invoices:
        invoices = invoices.filter(invoice_number__icontains=invoice_number_filter)

    # Calculate summary
    total_payments = len(payments)
    total_invoices = invoices.count()
    total_amount = sum(p.amount for p in payments)
    invoice_total_amount = invoices.aggregate(total=Sum('amount'))['total'] or 0

    payments_page_obj = _paginate_queryset(request, payments, per_page=15, page_param='payments_page')
    invoices_page_obj = _paginate_queryset(request, invoices, per_page=15, page_param='invoice_page')
    payments_page_base_query = _build_query_string(request, remove_keys=['payments_page'])
    invoices_page_base_query = _build_query_string(request, remove_keys=['invoice_page'])

    # Status breakdown for payments
    status_counts = {}
    for payment in payments:
        status = payment.get_status_display()
        status_counts[status] = status_counts.get(status, 0) + 1

    user_display_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

    return render(request, 'payments/customer_detail.html', {
        'customer_user': customer_user,
        'customer_profile': customer_profile,
        'payments': payments_page_obj,
        'invoices': invoices_page_obj,
        'payments_page_obj': payments_page_obj,
        'invoices_page_obj': invoices_page_obj,
        'payments_page_base_query': payments_page_base_query,
        'invoices_page_base_query': invoices_page_base_query,
        'total_payments': total_payments,
        'total_invoices': total_invoices,
        'total_amount': total_amount,
        'invoice_total_amount': invoice_total_amount,
        'customer_debt': _customer_debt_summary(customer_user),
        'status_counts': status_counts,
        'is_staff_user': is_staff_user,
        'staff_user_role': _user_role(request.user),
        'can_view_invoices': can_view_invoices,
        'filters': {
            'invoice_number': invoice_number_filter,
        },
        'user_display_name': user_display_name,
        'return_url': return_url,
    })


@login_required
def customers_list(request):
    """
    List all customers with their document counts for staff users.
    """
    is_staff_user = _is_staff_user(request.user)
    if not is_staff_user:
        return HttpResponseForbidden('این بخش فقط برای کاربران واحدها قابل دسترسی است.')

    # Get all customer profiles
    customers = UserProfile.objects.filter(role='customer').select_related('user').order_by('user__username')
    filters = {
        'q': (request.GET.get('q') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
    }
    if filters['q']:
        customers = customers.filter(
            Q(user__username__icontains=filters['q']) |
            Q(user__first_name__icontains=filters['q']) |
            Q(user__last_name__icontains=filters['q']) |
            Q(first_name__icontains=filters['q']) |
            Q(last_name__icontains=filters['q']) |
            Q(organization__icontains=filters['q']) |
            Q(city__icontains=filters['q']) |
            Q(province__icontains=filters['q']) |
            Q(phone__icontains=filters['q']) |
            Q(mobile__icontains=filters['q'])
        )
    if filters['status'] == 'active':
        customers = customers.filter(suspended=False, user__is_active=True)
    elif filters['status'] == 'suspended':
        customers = customers.filter(suspended=True)
    elif filters['status'] == 'inactive':
        customers = customers.filter(user__is_active=False)

    payment_stats = {
        row['user']: row
        for row in (
            PaymentRecord.objects
            .filter(user__profile__role='customer')
            .values('user')
            .annotate(
                payment_count=Count('id'),
                total_amount=Sum('amount'),
                latest_payment_date=Max('created_at'),
            )
        )
    }
    confirmed_payment_totals = {
        row['user']: row['total'] or 0
        for row in (
            PaymentRecord.objects
            .filter(
                user__profile__role='customer',
                status__in=[
                    PaymentRecord.STATUS_APPROVED,
                    PaymentRecord.STATUS_FINAL_APPROVED,
                ],
            )
            .values('user')
            .annotate(total=Sum('amount'))
        )
    }
    review_payment_totals = {
        row['user']: row['total'] or 0
        for row in (
            PaymentRecord.objects
            .filter(user__profile__role='customer')
            .exclude(status=PaymentRecord.STATUS_REJECTED)
            .values('user')
            .annotate(total=Sum('amount'))
        )
    }
    invoice_counts = {
        row['customer']: row['invoice_count']
        for row in (
            InvoiceRecord.objects
            .filter(customer__profile__role='customer')
            .values('customer')
            .annotate(invoice_count=Count('id'))
        )
    }
    invoice_totals = {
        row['customer']: row['total'] or 0
        for row in (
            InvoiceRecord.objects
            .filter(customer__profile__role='customer')
            .values('customer')
            .annotate(total=Sum('amount'))
        )
    }

    # Calculate counts for each customer
    customer_data = []
    for profile in customers:
        stats = payment_stats.get(profile.user_id, {})
        invoice_total = invoice_totals.get(profile.user_id, 0)
        confirmed_payment_total = confirmed_payment_totals.get(profile.user_id, 0)
        review_payment_total = review_payment_totals.get(profile.user_id, 0)

        customer_data.append({
            'profile': profile,
            'user': profile.user,
            'payment_count': stats.get('payment_count') or 0,
            'invoice_count': invoice_counts.get(profile.user_id, 0),
            'total_amount': stats.get('total_amount') or 0,
            'invoice_total': invoice_total,
            'confirmed_debt': invoice_total - confirmed_payment_total,
            'review_debt': invoice_total - review_payment_total,
            'latest_payment_date': stats.get('latest_payment_date'),
        })

    user_display_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
    page_obj = _paginate_queryset(request, customer_data, per_page=15, page_param='page')
    page_base_query = _build_query_string(request, remove_keys=['page'])

    return render(request, 'payments/customers_list.html', {
        'customer_data': page_obj,
        'page_obj': page_obj,
        'page_base_query': page_base_query,
        'is_staff_user': is_staff_user,
        'can_manage_users': _can_manage_users(request.user),
        'user_display_name': user_display_name,
        'filters': filters,
    })


@login_required
@require_POST
def reset_user_password(request, user_id):
    """
    Reset a user's password to a temporary numeric password and force them to change it.
    Only accessible to users with management permissions.
    """
    if not _can_manage_users(request.user):
        return HttpResponseForbidden('شما دسترسی ریست رمز عبور را ندارید.')

    target_user = get_object_or_404(User, id=user_id)
    temp_password = _suggest_five_digit_password()

    from django.http import JsonResponse

    email_sent = False
    email_note = 'برای این کاربر ایمیل ثبت نشده است؛ رمز جدید فقط به مدیر سیستم نمایش داده شد.'
    if target_user.email:
        try:
            email_sent, email_error = _send_temporary_password_email(target_user, temp_password)
            if email_sent:
                email_note = f'رمز جدید به ایمیل {target_user.email} ارسال شد.'
            else:
                email_note = email_error
        except Exception:
            email_note = 'ارسال ایمیل انجام نشد؛ رمز جدید فقط به مدیر سیستم نمایش داده شد.'

    target_user.set_password(temp_password)
    target_user.save()

    # Invalidate all sessions for the target user
    for session in Session.objects.all():
        session_data = session.get_decoded()
        if session_data.get('_auth_user_id') == str(target_user.id):
            session.delete()

    profile = getattr(target_user, 'profile', None)
    if profile:
        profile.force_password_change = True
        profile.save(update_fields=['force_password_change'])

    _log_system_activity(
        request.user,
        target_user,
        SystemActivityLog.ACTION_PASSWORD_RESET,
        f'رمز عبور کاربر ریست شد. {email_note} کاربر ملزم به تغییر رمز در ورود بعدی شد.',
    )

    message = 'رمز عبور کاربر با موفقیت ریست شد. این رمز فقط همین لحظه نمایش داده می‌شود.'
    if email_sent:
        message = 'رمز عبور کاربر با موفقیت ریست شد و به ایمیل کاربر ارسال شد. این رمز فقط همین لحظه نمایش داده می‌شود.'
    elif not target_user.email:
        message = 'رمز عبور کاربر با موفقیت ریست شد. برای این کاربر ایمیل ثبت نشده است؛ رمز را همین حالا به کاربر اطلاع دهید.'
    else:
        message = 'رمز عبور کاربر با موفقیت ریست شد. ارسال ایمیل انجام نشد؛ رمز را همین حالا به کاربر اطلاع دهید.'

    return JsonResponse({
        'success': True,
        'temp_password': temp_password,
        'message': message,
    })




