import jdatetime
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .forms import PaymentRecordForm
from .models import PaymentRecord, PaymentReceipt, UserProfile


STAFF_ROLES = {'staff', 'finance', 'commercial'}


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
    if _is_staff_user(user):
        return PaymentRecord.objects.all().prefetch_related('receipts').order_by('-id')
    return PaymentRecord.objects.filter(user=user).prefetch_related('receipts').order_by('-id')


def _parse_jalali_date(date_text):
    if not date_text:
        return None
    try:
        return jdatetime.datetime.strptime(date_text, '%Y/%m/%d').date()
    except ValueError:
        return None


def _apply_record_filters(records, request, is_staff_user):
    filters = {
        'first_name': (request.GET.get('first_name') or '').strip(),
        'last_name': (request.GET.get('last_name') or '').strip(),
        'phone': (request.GET.get('phone') or '').strip(),
        'city': (request.GET.get('city') or '').strip(),
        'amount': (request.GET.get('amount') or '').replace(',', '').strip(),
        'pay_date': (request.GET.get('pay_date') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
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


def _can_customer_edit_payment(user, payment):
    return (
        user.is_authenticated
        and payment.user_id == user.id
        and payment.status == 'rejected'
    )


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
            payment.save()
            _save_receipts(payment, form)
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
        'status_choices': PaymentRecord.STATUS_CHOICES,
    })


@login_required
def success(request):
    records = _records_for_user(request.user)
    return render(request, 'payments/success.html', {
        'records': records
    })


@login_required
@require_POST
def mark_reviewed(request, payment_id):
    if not _is_staff_user(request.user):
        return HttpResponseForbidden('You do not have permission to review documents.')

    payment = get_object_or_404(PaymentRecord, id=payment_id)
    if payment.status == 'pending':
        payment.status = 'reviewed'
        payment.save(update_fields=['status'])

    return redirect(request.META.get('HTTP_REFERER') or 'submit')


@login_required
@require_POST
def mark_incomplete(request, payment_id):
    if not _is_staff_user(request.user):
        return HttpResponseForbidden('You do not have permission to review documents.')

    payment = get_object_or_404(PaymentRecord, id=payment_id)
    if payment.status in {'pending', 'reviewed'}:
        payment.status = 'rejected'
        payment.save(update_fields=['status'])

    return redirect(request.META.get('HTTP_REFERER') or 'submit')


@login_required
def edit_payment(request, payment_id):
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if _is_staff_user(request.user):
        return HttpResponseForbidden('Staff users cannot edit customer payment records.')

    if payment.user_id != request.user.id:
        return HttpResponseForbidden('You can only edit your own payment records.')

    if payment.status == 'pending':
        return HttpResponseForbidden('This record is under review and cannot be edited.')

    if payment.status != 'rejected':
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
            payment.status = 'pending'
            payment.save()
            _save_receipts(payment, form)
            return redirect('submit')
    else:
        form = PaymentRecordForm(instance=payment, initial=initial_data)

    return render(request, 'payments/edit_payment.html', {
        'form': form,
        'payment': payment,
    })
