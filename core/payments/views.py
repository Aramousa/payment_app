import jdatetime

from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .forms import CounterpartyForm, PaymentRecordForm, StaffStatusUpdateForm
from .models import Counterparty, PaymentActivityLog, PaymentRecord, PaymentReceipt, UserProfile


STAFF_ROLES = {'staff', 'finance', 'commercial'}
CUSTOMER_STATUSES = [
    (PaymentRecord.STATUS_PENDING, 'در حال بررسی'),
    (PaymentRecord.STATUS_APPROVED, 'تایید شده'),
    (PaymentRecord.STATUS_REJECTED, 'رد شده'),
    (PaymentRecord.STATUS_INCOMPLETE, 'ناقص'),
]


def _is_staff_user(user):
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    try:
        return user.profile.role in STAFF_ROLES
    except UserProfile.DoesNotExist:
        return False


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


def _apply_record_filters(records, request, is_staff_user):
    filters = {
        'first_name': (request.GET.get('first_name') or '').strip(),
        'last_name': (request.GET.get('last_name') or '').strip(),
        'phone': (request.GET.get('phone') or '').strip(),
        'city': (request.GET.get('city') or '').strip(),
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
        if filters['counterparty'].isdigit():
            records = records.filter(counterparty_id=int(filters['counterparty']))

    if filters['amount'].isdigit():
        records = records.filter(amount=int(filters['amount']))

    parsed_date = _parse_jalali_date(filters['pay_date'])
    if parsed_date:
        records = records.filter(pay_date=parsed_date)

    valid_statuses = {choice[0] for choice in PaymentRecord.STATUS_CHOICES}
    if filters['status'] in valid_statuses:
        records = records.filter(status=filters['status'])

    return records, filters


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


@login_required
def create_payment(request):
    profile = None
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = None

    initial_data = _account_initial_data(request.user, profile)
    is_staff_user = _is_staff_user(request.user)

    if request.method == 'POST':
        if is_staff_user:
            return HttpResponseForbidden('Staff users cannot create payment records from this form.')
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

    return render(request, 'payments/form.html', {
        'form': form,
        'records': records,
        'is_staff_user': is_staff_user,
        'filters': active_filters,
        'status_choices': PaymentRecord.STATUS_CHOICES if is_staff_user else CUSTOMER_STATUSES,
        'counterparties': Counterparty.objects.all() if is_staff_user else [],
        'staff_action_choices': PaymentRecord.STATUS_CHOICES,
    })


@login_required
def success(request):
    records = _records_for_user(request.user)
    return render(request, 'payments/success.html', {'records': records})


@login_required
@require_POST
def staff_update_status(request, payment_id):
    if not _is_staff_user(request.user):
        return HttpResponseForbidden('You do not have permission to review documents.')

    payment = get_object_or_404(PaymentRecord, id=payment_id)
    form = StaffStatusUpdateForm(request.POST)
    if not form.is_valid():
        return redirect(request.META.get('HTTP_REFERER') or 'submit')

    from_status = payment.status
    payment.status = form.cleaned_data['status']
    payment.last_staff_note = form.cleaned_data['note'] or ''

    selected_counterparty = form.cleaned_data['counterparty']
    if selected_counterparty:
        payment.counterparty = selected_counterparty

    payment.save(update_fields=['status', 'last_staff_note', 'counterparty'])

    _log_activity(
        payment,
        request.user,
        PaymentActivityLog.ACTION_STATUS_CHANGED,
        from_status=from_status,
        to_status=payment.status,
        note=payment.last_staff_note,
    )

    return redirect(request.META.get('HTTP_REFERER') or 'submit')


@login_required
def edit_payment(request, payment_id):
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if _is_staff_user(request.user):
        return HttpResponseForbidden('Staff users cannot edit customer payment records.')

    if payment.user_id != request.user.id:
        return HttpResponseForbidden('You can only edit your own payment records.')

    if payment.status != PaymentRecord.STATUS_INCOMPLETE:
        return HttpResponseForbidden('Only incomplete records can be edited.')

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
            payment.save()
            _save_receipts(payment, form)
            _log_activity(payment, request.user, PaymentActivityLog.ACTION_EDITED, from_status=from_status, to_status=payment.status)
            return redirect('submit')
    else:
        form = PaymentRecordForm(instance=payment, initial=initial_data)

    return render(request, 'payments/edit_payment.html', {'form': form, 'payment': payment})


@login_required
def payment_timeline(request, payment_id):
    payment = get_object_or_404(PaymentRecord.objects.select_related('user', 'counterparty'), id=payment_id)
    if not _is_staff_user(request.user) and payment.user_id != request.user.id:
        return HttpResponseForbidden('You can only view your own payment record timeline.')

    _log_activity(payment, request.user, PaymentActivityLog.ACTION_VIEWED, note='مشاهده تاریخچه')
    logs = payment.activity_logs.select_related('actor').all()

    return render(request, 'payments/timeline.html', {'payment': payment, 'logs': logs, 'is_staff_user': _is_staff_user(request.user)})


@login_required
def counterparties_manage(request):
    if not _is_staff_user(request.user):
        return HttpResponseForbidden('You do not have permission to manage counterparties.')

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
    if not _is_staff_user(request.user):
        return HttpResponseForbidden('You do not have permission to manage counterparties.')

    counterparty = get_object_or_404(Counterparty, id=counterparty_id)

    if request.method == 'POST':
        form = CounterpartyForm(request.POST, instance=counterparty)
        if form.is_valid():
            form.save()
            return redirect('counterparties_manage')
    else:
        form = CounterpartyForm(instance=counterparty)

    return render(request, 'payments/counterparty_edit.html', {'form': form, 'counterparty': counterparty})
