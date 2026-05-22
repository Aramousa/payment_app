import os
import re
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone

from .models import InvoiceExtractionJob


PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff'}
PDF_EXTENSION = '.pdf'


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


def detect_file_kind(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext == PDF_EXTENSION:
        return 'pdf'
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    return 'unsupported'


def create_preview_extraction_job(uploaded_file, requested_by=None):
    job = InvoiceExtractionJob(
        requested_by=requested_by,
        source=InvoiceExtractionJob.SOURCE_PREVIEW,
        original_filename=uploaded_file.name or '',
        file_kind=detect_file_kind(uploaded_file.name),
    )
    job.file.save(uploaded_file.name or 'invoice-upload', uploaded_file, save=True)
    return job


def create_invoice_extraction_job(invoice, requested_by=None):
    if not invoice.attachment:
        return None
    job = InvoiceExtractionJob(
        invoice=invoice,
        requested_by=requested_by,
        source=InvoiceExtractionJob.SOURCE_INVOICE,
        original_filename=Path(invoice.attachment.name).name,
        file_kind=detect_file_kind(invoice.attachment.name),
    )
    invoice.attachment.open('rb')
    try:
        job.file.save(Path(invoice.attachment.name).name, ContentFile(invoice.attachment.read()), save=True)
    finally:
        invoice.attachment.close()
    return job


def process_invoice_extraction_job(job_id):
    job = InvoiceExtractionJob.objects.get(id=job_id)
    job.status = InvoiceExtractionJob.STATUS_PROCESSING
    job.started_at = timezone.now()
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'error_message'])

    try:
        result = extract_invoice_file(job.file.path, original_name=job.original_filename or job.file.name)
        job.file_kind = result.get('file_kind', job.file_kind)
        job.text_source = result.get('text_source', '')
        job.raw_text = result.get('raw_text', '')
        job.result_json = result
        job.warnings = result.get('warnings', [])
        job.status = InvoiceExtractionJob.STATUS_DONE
        job.finished_at = timezone.now()
        job.save(update_fields=[
            'file_kind',
            'text_source',
            'raw_text',
            'result_json',
            'warnings',
            'status',
            'finished_at',
        ])
    except Exception as exc:
        job.status = InvoiceExtractionJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at'])
    return job.id


def extract_invoice_file(file_path, original_name=''):
    file_kind = detect_file_kind(original_name or file_path)
    warnings = []
    if file_kind == 'pdf':
        raw_text, text_source, pdf_warnings = extract_pdf_text_or_ocr(file_path)
        warnings.extend(pdf_warnings)
    elif file_kind == 'image':
        raw_text, text_source, ocr_warnings = extract_image_text(file_path)
        warnings.extend(ocr_warnings)
    else:
        raw_text = ''
        text_source = ''
        warnings.append('فرمت فایل برای استخراج اطلاعات پشتیبانی نمی‌شود.')

    normalized_text = normalize_text(raw_text)
    parsed = parse_invoice_text(normalized_text)
    parsed['raw_text'] = normalized_text
    parsed['raw_text_preview'] = normalized_text[:1200]
    parsed['file_kind'] = file_kind
    parsed['text_source'] = text_source
    parsed['warnings'] = warnings + parsed.get('warnings', [])
    parsed['ok'] = bool(parsed.get('fields'))
    parsed['message'] = 'اطلاعات پیشنهادی از فایل خوانده شد.' if parsed['ok'] else 'متن فایل خوانده شد، اما فیلد قابل اطمینانی تشخیص داده نشد.'
    return parsed


def extract_pdf_text_or_ocr(file_path):
    warnings = []
    text = ''
    try:
        import fitz

        with fitz.open(file_path) as doc:
            text = '\n'.join(page.get_text('text') or '' for page in doc)
            if normalize_text(text):
                return text, 'pymupdf_text', warnings

            page_texts = []
            for page_index, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                    temp.write(pix.tobytes('png'))
                    temp_path = temp.name
                try:
                    page_text, _source, page_warnings = extract_image_text(temp_path)
                    warnings.extend([f'صفحه {page_index + 1}: {warning}' for warning in page_warnings])
                    page_texts.append(page_text)
                finally:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
            return '\n'.join(page_texts), 'paddleocr_pdf', warnings
    except ImportError:
        warnings.append('PyMuPDF نصب نیست؛ تلاش با pypdf انجام شد.')
    except Exception as exc:
        warnings.append(f'خواندن PDF با PyMuPDF ناموفق بود: {exc}')

    try:
        from pypdf import PdfReader

        with open(file_path, 'rb') as handle:
            reader = PdfReader(handle)
            text = '\n'.join((page.extract_text() or '') for page in reader.pages)
        if normalize_text(text):
            return text, 'pypdf_text', warnings
    except ImportError:
        warnings.append('pypdf نصب نیست.')
    except Exception as exc:
        warnings.append(f'خواندن PDF با pypdf ناموفق بود: {exc}')

    warnings.append('متن قابل استخراج از PDF پیدا نشد. اگر PDF اسکن‌شده باشد، PyMuPDF و PaddleOCR لازم است.')
    return '', '', warnings


def extract_image_text(file_path):
    warnings = []
    prepared_path = file_path
    temp_path = ''
    try:
        prepared_path, temp_path, cv_warnings = preprocess_image(file_path)
        warnings.extend(cv_warnings)
        text, ocr_warnings = paddle_ocr_image(prepared_path)
        warnings.extend(ocr_warnings)
        return text, 'paddleocr_image', warnings
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def preprocess_image(file_path):
    try:
        import cv2

        image = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return file_path, '', ['OpenCV نتوانست تصویر را بخواند.']
        image = cv2.fastNlMeansDenoising(image, None, 12, 7, 21)
        image = cv2.adaptiveThreshold(
            image,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        temp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp.close()
        cv2.imwrite(temp.name, image)
        return temp.name, temp.name, []
    except ImportError:
        return file_path, '', ['OpenCV نصب نیست؛ تصویر بدون بهبود کیفیت به OCR ارسال شد.']
    except Exception as exc:
        return file_path, '', [f'بهبود کیفیت تصویر با OpenCV ناموفق بود: {exc}']


def paddle_ocr_image(file_path):
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return '', ['PaddleOCR نصب نیست؛ امکان OCR عکس یا PDF اسکن‌شده وجود ندارد.']

    try:
        ocr = get_paddle_ocr()
        result = ocr.ocr(file_path, cls=True)
        lines = []
        for page in result or []:
            for item in page or []:
                try:
                    lines.append(item[1][0])
                except Exception:
                    continue
        return '\n'.join(lines), []
    except Exception as exc:
        return '', [f'اجرای PaddleOCR ناموفق بود: {exc}']


_PADDLE_OCR = None


def get_paddle_ocr():
    global _PADDLE_OCR
    if _PADDLE_OCR is None:
        from paddleocr import PaddleOCR

        _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang='fa', show_log=False)
    return _PADDLE_OCR


def _line_after_label(text, labels):
    for label in labels:
        pattern = rf'{label}\s*[:：\-]?\s*([^\n]+)'
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(' :：-')
            if value:
                return value
    return ''


def parse_invoice_text(text):
    fields = {
        'invoice_number': _extract_invoice_number(text),
        'reference_number': _extract_reference_number(text),
        'amount': _extract_amount(text),
        'invoice_date': _extract_invoice_date(text),
    }
    fields = {key: {'value': value, 'confidence': 0.8, 'source': 'parser'} for key, value in fields.items() if value}
    return {
        'fields': fields,
        'warnings': [],
    }


def flatten_fields(result):
    fields = result.get('fields') or {}
    return {
        key: value.get('value') if isinstance(value, dict) else value
        for key, value in fields.items()
        if value
    }


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
            import jdatetime

            return jdatetime.date.fromgregorian(year=year, month=month, day=day).strftime('%Y/%m/%d')
        except ValueError:
            return ''
    try:
        import jdatetime

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
