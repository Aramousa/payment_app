import jdatetime
from openpyxl import Workbook
from urllib.parse import urlencode

from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .forms import CounterpartyForm, PaymentRecordForm, StaffStatusUpdateForm
from .models import Counterparty, PaymentActivityLog, PaymentRecord, PaymentReceipt, UserProfile


STAFF_ROLES = {'staff', 'finance', 'commercial'}
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
                'time': log.created_at,
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
        records = records.filter(amount=int(filters['amount']))

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


def _payer_profiles_for_user(user):
    if not user or not user.is_authenticated:
        return []
    records = (
        PaymentRecord.objects
        .filter(user=user)
        .values(
            'payer_account_number',
            'payer_full_name',
            'payer_bank_name',
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
            'payer_account_number': (row.get('payer_account_number') or '').strip(),
            'payer_full_name': (row.get('payer_full_name') or '').strip(),
            'payer_bank_name': (row.get('payer_bank_name') or '').strip(),
            'beneficiary_bank_name': (row.get('beneficiary_bank_name') or '').strip(),
            'beneficiary_account_number': (row.get('beneficiary_account_number') or '').strip(),
            'beneficiary_account_owner': (row.get('beneficiary_account_owner') or '').strip(),
        }
        if not all(values.values()):
            continue
        if 'Z' in values.values():
            continue
        key = tuple(values[field] for field in (
            'payer_account_number',
            'payer_full_name',
            'payer_bank_name',
            'beneficiary_bank_name',
            'beneficiary_account_number',
            'beneficiary_account_owner',
        ))
        if key in seen:
            continue
        seen.add(key)
        profiles.append(values)
    return profiles


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

    if request.method == 'POST':
        if is_staff_user:
            return HttpResponseForbidden('کاربران واحدها امکان ثبت سند از این فرم را ندارند.')
        form = PaymentRecordForm(request.POST, request.FILES, initial=initial_data)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.user = request.user
            payment.first_name = initial_data['first_name']
            payment.last_name = initial_data['last_name']
            payment.organization = initial_data['organization']
            payment.city = initial_data['city']
            payment.phone = initial_data['phone']
            payment.status = PaymentRecord.STATUS_PENDING
            payment.save()
            _save_receipts(payment, form)
            _log_activity(payment, request.user, PaymentActivityLog.ACTION_CREATED, to_status=payment.status)
            return redirect('success')
    else:
        form = PaymentRecordForm(initial=initial_data)

    records = _records_for_user(request.user)
    records, active_filters = _apply_record_filters(records, request, is_staff_user)
    records, current_sort, current_sort_dir, sort_base_query = _apply_record_sort(records, request)
    records = _enrich_records(records, staff_role=staff_role, is_system_admin=is_system_admin)
    user_display_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

    return render(request, 'payments/form.html', {
        'form': form,
        'records': records,
        'is_staff_user': is_staff_user,
        'filters': active_filters,
        'status_choices': PaymentRecord.STATUS_CHOICES if is_staff_user else CUSTOMER_STATUSES,
        'counterparties': Counterparty.objects.all() if is_staff_user else [],
        'staff_user_role': staff_role,
        'staff_role_label': _staff_role_label(staff_role),
        'can_manage_counterparties': is_system_admin,
        'can_export_records': is_system_admin or staff_role in {'finance', 'commercial'},
        'is_system_admin': is_system_admin,
        'user_display_name': user_display_name,
        'payer_profiles': _payer_profiles_for_user(request.user) if not is_staff_user else [],
        'current_sort': current_sort,
        'current_sort_dir': current_sort_dir,
        'sort_base_query': sort_base_query,
        'customer_info': initial_data,
    })


@login_required
def success(request):
    records = _records_for_user(request.user)
    return render(request, 'payments/success.html', {'records': records})


@login_required
@require_POST
def staff_update_status(request, payment_id):
    redirect_target = request.META.get('HTTP_REFERER') or 'submit'

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
            return redirect('submit')
    else:
        form = PaymentRecordForm(instance=payment, initial=initial_data)

    return render(request, 'payments/edit_payment.html', {
        'form': form,
        'payment': payment,
        'payer_profiles': _payer_profiles_for_user(request.user),
        'customer_info': initial_data,
    })


@login_required
def payment_timeline(request, payment_id):
    payment = get_object_or_404(PaymentRecord.objects.select_related('user', 'counterparty'), id=payment_id)
    if not _is_staff_user(request.user) and payment.user_id != request.user.id:
        return HttpResponseForbidden('فقط امکان مشاهده تاریخچه اسناد خودتان وجود دارد.')

    _log_activity(payment, request.user, PaymentActivityLog.ACTION_VIEWED, note='مشاهده تاریخچه')
    logs = payment.activity_logs.select_related('actor').all()

    return render(request, 'payments/timeline.html', {'payment': payment, 'logs': logs, 'is_staff_user': _is_staff_user(request.user)})


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
    return render(request, 'payments/counterparties.html', {'form': form, 'counterparties': counterparties})


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
def export_records(request):
    if not _is_staff_user(request.user):
        return HttpResponseForbidden('شما دسترسی خروجی گرفتن از رکوردها را ندارید.')

    role = _user_role(request.user)
    if not request.user.is_superuser and role not in {'finance', 'commercial'}:
        return HttpResponseForbidden('خروجی فقط برای کاربران مالی و بازرگانی فعال است.')

    records = _records_for_user(request.user)
    records, _ = _apply_record_filters(records, request, is_staff_user=True)

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
            payment.created_at.strftime('%Y-%m-%d %H:%M:%S') if payment.created_at else '',
        ])

    wb.save(response)
    return response





