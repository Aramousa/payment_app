import datetime

import jdatetime
from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def thousand_sep(value):
    try:
        amount = int(str(value).replace(',', '').strip())
    except (ValueError, TypeError):
        return value
    return '{:,}'.format(amount)


def _to_jalali(value):
    if not value:
        return None
    if isinstance(value, (jdatetime.datetime, jdatetime.date)):
        return value
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
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
