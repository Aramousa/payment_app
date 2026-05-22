import os
import re

import jdatetime
from PIL import Image, ImageOps


PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff'}


def normalize_digits(value):
    return str(value or '').translate(PERSIAN_DIGITS)


def normalize_text(value):
    text = normalize_digits(value)
    text = text.replace('\u200c', ' ')
    text = text.replace('ك', 'ک').replace('ي', 'ی')
    text = text.replace('٬', ',').replace('٫', '.')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\r\n?', '\n', text)
    return text.strip()


def _extract_text_with_optional_libraries(uploaded_file):
    uploaded_file.seek(0)
    ext = os.path.splitext(uploaded_file.name or '')[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return _extract_text_from_image(uploaded_file)
    if ext != '.pdf':
        return '', 'خواندن خودکار فقط برای فایل PDF یا تصویر فاکتور فعال است.'

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


def _extract_text_from_image(uploaded_file):
    try:
        import pytesseract
    except ImportError:
        return '', 'برای خواندن اطلاعات از عکس باید pytesseract و موتور Tesseract OCR با زبان فارسی روی سرور نصب باشد.'

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        image = image.convert('L')
        image = ImageOps.autocontrast(image)
        text = pytesseract.image_to_string(image, lang='fas+eng', config='--psm 6')
        return text, ''
    except pytesseract.TesseractNotFoundError:
        return '', 'موتور Tesseract OCR روی سرور پیدا نشد. برای خواندن عکس فاکتور باید Tesseract و زبان فارسی نصب شود.'
    except pytesseract.TesseractError as exc:
        message = str(exc)
        if 'fas' in message or 'traineddata' in message:
            return '', 'زبان فارسی Tesseract نصب نیست. فایل زبان fas.traineddata باید روی سرور فعال باشد.'
        return '', 'خواندن متن از عکس فاکتور انجام نشد.'
    except Exception:
        return '', 'فایل تصویر قابل خواندن نبود یا OCR روی آن موفق نشد.'


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
        pattern = rf'{label}[^\d\n]{{0,40}}([0-9][0-9,\s\.]{{3,}})'
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            digits = re.sub(r'\D', '', match.group(1))
            if digits:
                return digits

    labeled_line_candidates = []
    for line in text.splitlines():
        if not re.search(r'ریال|تومان|rial|irr|toman', line, flags=re.IGNORECASE):
            continue
        if not re.search(r'کل|جمع|قابل\s*پرداخت|مانده|total|grand', line, flags=re.IGNORECASE):
            continue
        for match in re.finditer(r'(?<!\d)([0-9]{1,3}(?:[, ]?[0-9]{3})+|[0-9]{5,})(?!\d)', line):
            digits = re.sub(r'\D', '', match.group(1))
            if digits:
                labeled_line_candidates.append(int(digits))
    if labeled_line_candidates:
        return str(max(labeled_line_candidates))

    currency_candidates = []
    for line in text.splitlines():
        if not re.search(r'ریال|تومان|rial|irr|toman', line, flags=re.IGNORECASE):
            continue
        for match in re.finditer(r'(?<!\d)([0-9]{1,3}(?:[, ]?[0-9]{3})+|[0-9]{5,})(?!\d)', line):
            digits = re.sub(r'\D', '', match.group(1))
            if digits:
                currency_candidates.append(int(digits))
    unique_candidates = sorted(set(currency_candidates))
    if len(unique_candidates) == 1:
        return str(unique_candidates[0])
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
    ext = os.path.splitext(uploaded_file.name or '')[1].lower()
    text, warning = _extract_text_with_optional_libraries(uploaded_file)
    text = normalize_text(text)
    if not text:
        file_kind = 'عکس' if ext in IMAGE_EXTENSIONS else 'PDF'
        return {
            'ok': False,
            'message': warning or f'متنی از {file_kind} خوانده نشد. اگر فایل اسکن‌شده یا تصویر باشد، OCR فارسی لازم است.',
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
        'message': 'اطلاعات پیشنهادی از فایل خوانده شد.' if fields else 'متن فایل خوانده شد، اما فیلد قابل اطمینانی تشخیص داده نشد.',
        'fields': fields,
        'raw_text_preview': text[:1200],
    }
