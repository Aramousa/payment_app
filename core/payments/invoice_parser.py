import os
import re

import jdatetime


PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_digits(value):
    return str(value or '').translate(PERSIAN_DIGITS)


def normalize_text(value):
    text = normalize_digits(value)
    text = text.replace('\u200c', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\r\n?', '\n', text)
    return text.strip()


def _extract_text_with_optional_libraries(uploaded_file):
    uploaded_file.seek(0)
    ext = os.path.splitext(uploaded_file.name or '')[1].lower()
    if ext != '.pdf':
        return '', 'در حال حاضر خواندن خودکار فقط برای فایل PDF فعال است.'

    errors = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(uploaded_file)
        return '\n'.join((page.extract_text() or '') for page in reader.pages), ''
    except ImportError:
        errors.append('pypdf نصب نیست')
    except Exception as exc:
        errors.append(f'pypdf: {exc}')

    uploaded_file.seek(0)
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(uploaded_file)
        return '\n'.join((page.extract_text() or '') for page in reader.pages), ''
    except ImportError:
        errors.append('PyPDF2 نصب نیست')
    except Exception as exc:
        errors.append(f'PyPDF2: {exc}')

    uploaded_file.seek(0)
    try:
        import pdfplumber

        with pdfplumber.open(uploaded_file) as pdf:
            return '\n'.join((page.extract_text() or '') for page in pdf.pages), ''
    except ImportError:
        errors.append('pdfplumber نصب نیست')
    except Exception as exc:
        errors.append(f'pdfplumber: {exc}')

    return '', 'برای خواندن PDF متنی باید یکی از کتابخانه‌های pypdf، PyPDF2 یا pdfplumber روی سرور نصب باشد.'


def _line_after_label(text, labels):
    for label in labels:
        pattern = rf'{label}\s*[:：\-]?\s*([^\n]+)'
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(' :：-')
            if value:
                return value
    return ''


def _extract_invoice_number(text):
    value = _line_after_label(text, [
        r'شماره\s*فاکتور',
        r'شماره\s*صورتحساب',
        r'فاکتور\s*شماره',
        r'invoice\s*(?:no|number)',
    ])
    if not value:
        match = re.search(r'\b(?:INV|FA|FACT|INVOICE)[\-/]?[A-Z0-9\-/]{2,}\b', text, flags=re.IGNORECASE)
        value = match.group(0) if match else ''
    return _clean_short_value(value)


def _extract_reference_number(text):
    value = _line_after_label(text, [
        r'شماره\s*حواله',
        r'شماره\s*ارجاع',
        r'شماره\s*مرجع',
        r'کد\s*رهگیری',
        r'reference\s*(?:no|number)',
    ])
    return _clean_short_value(value)


def _extract_amount(text):
    amount_labels = [
        r'مبلغ\s*کل',
        r'جمع\s*کل',
        r'جمع\s*فاکتور',
        r'مبلغ\s*قابل\s*پرداخت',
        r'مانده\s*قابل\s*پرداخت',
        r'total\s*amount',
        r'grand\s*total',
    ]
    for label in amount_labels:
        pattern = rf'{label}\s*[:：\-]?\s*([0-9,\s]+)'
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            digits = re.sub(r'\D', '', match.group(1))
            if digits:
                return digits

    candidates = []
    for match in re.finditer(r'(?<!\d)([0-9]{1,3}(?:[, ]?[0-9]{3}){1,})(?!\d)', text):
        digits = re.sub(r'\D', '', match.group(1))
        if len(digits) >= 5:
            candidates.append(int(digits))
    if candidates:
        return str(max(candidates))
    return ''


def _extract_invoice_date(text):
    label_value = _line_after_label(text, [
        r'تاریخ\s*فاکتور',
        r'تاریخ\s*صورتحساب',
        r'تاریخ\s*صدور',
        r'invoice\s*date',
    ])
    date_text = _find_date(label_value) or _find_date(text)
    if not date_text:
        return ''

    parts = [int(part) for part in re.split(r'[\/\-.]', date_text) if part]
    if len(parts) != 3:
        return ''
    year, month, day = parts
    if year < 100:
        year += 1400 if year < 50 else 1300
    if year > 1700:
        try:
            return jdatetime.date.fromgregorian(year=year, month=month, day=day).strftime('%Y/%m/%d')
        except ValueError:
            return ''
    try:
        return jdatetime.date(year, month, day).strftime('%Y/%m/%d')
    except ValueError:
        return ''


def _find_date(text):
    match = re.search(r'(?<!\d)(\d{2,4}[\/\-.]\d{1,2}[\/\-.]\d{1,2})(?!\d)', text or '')
    return match.group(1) if match else ''


def _clean_short_value(value):
    value = normalize_digits(value)
    value = re.split(r'\s{2,}|\t|\n', value)[0]
    value = value.strip(' :：-،,')
    return value[:80]


def parse_invoice_upload(uploaded_file):
    text, warning = _extract_text_with_optional_libraries(uploaded_file)
    text = normalize_text(text)
    if not text:
        return {
            'ok': False,
            'message': warning or 'متنی از PDF خوانده نشد. اگر فایل اسکن‌شده یا عکس باشد، برای خواندن آن OCR فارسی لازم است.',
            'fields': {},
            'raw_text_preview': '',
        }

    fields = {
        'invoice_number': _extract_invoice_number(text),
        'reference_number': _extract_reference_number(text),
        'amount': _extract_amount(text),
        'invoice_date': _extract_invoice_date(text),
    }
    fields = {key: value for key, value in fields.items() if value}

    return {
        'ok': bool(fields),
        'message': 'اطلاعات پیشنهادی از PDF خوانده شد.' if fields else 'متن PDF خوانده شد، اما فیلد قابل اطمینانی تشخیص داده نشد.',
        'fields': fields,
        'raw_text_preview': text[:1200],
    }
