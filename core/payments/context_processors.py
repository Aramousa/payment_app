from django.utils import timezone

from .models import LoginAdvertisement, PaymentRecord, InvoiceRecord, UserProfile


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

        today = timezone.now().date()
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
