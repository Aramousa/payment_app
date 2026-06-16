import datetime

import jdatetime
from django import template
from django.conf import settings
from django.utils import timezone
from zoneinfo import ZoneInfo

register = template.Library()


DISPLAY_TIME_ZONE = ZoneInfo(getattr(settings, 'APP_DISPLAY_TIME_ZONE', 'Asia/Tehran'))


_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _to_persian_num(text):
    return str(text).translate(_FA_DIGITS)


@register.filter
def thousand_sep(value):
    try:
        amount = int(str(value).replace(',', '').replace('،', '').strip())
    except (ValueError, TypeError):
        return value
    return _to_persian_num('{:,}'.format(amount))


def _to_jalali(value):
    if not value:
        return None
    if isinstance(value, (jdatetime.datetime, jdatetime.date)):
        return value
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value, DISPLAY_TIME_ZONE)
        return jdatetime.datetime.fromgregorian(datetime=value)
    if isinstance(value, datetime.date):
        return jdatetime.date.fromgregorian(date=value)
    return None


@register.filter
def jalali_date(value, date_format='%Y/%m/%d'):
    jalali_value = _to_jalali(value)
    if not jalali_value:
        return ''
    return jalali_value.strftime(date_format)


@register.filter
def jalali_datetime(value, date_format='%Y/%m/%d %H:%M'):
    return jalali_date(value, date_format)


@register.simple_tag
def pagination_window(page_obj, side_count=2, edge_count=1):
    if not page_obj:
        return []
    current = page_obj.number
    total = page_obj.paginator.num_pages
    visible_pages = set()

    for page_number in range(1, min(edge_count, total) + 1):
        visible_pages.add(page_number)
    for page_number in range(max(total - edge_count + 1, 1), total + 1):
        visible_pages.add(page_number)
    for page_number in range(max(current - side_count, 1), min(current + side_count, total) + 1):
        visible_pages.add(page_number)

    pages = []
    previous = 0
    for page_number in sorted(visible_pages):
        if previous and page_number - previous > 1:
            pages.append('...')
        pages.append(page_number)
        previous = page_number
    return pages
