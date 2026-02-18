from django.utils import timezone

from .models import LoginAdvertisement


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
