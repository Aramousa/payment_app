import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
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
    text = text.replace('‌', ' ').replace('‏', '').replace('‎', '')
    text = text.replace('ك', 'ک').replace('ي', 'ی').replace('ئ', 'ی')
    text = text.replace('٬', ',').replace('٫', '.').replace('٫', '.').replace('٬', ',')
    # نرمال‌سازی فاصله
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\r\n?', '\n', text)
    # حذف خطوط کاملاً خالی متوالی
    text = re.sub(r'\n{3,}', '\n\n', text)
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
        job.save(update_fields=['file_kind', 'text_source', 'raw_text', 'result_json',
                                'warnings', 'status', 'finished_at'])
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
    parsed['raw_text_preview'] = normalized_text[:1500]
    parsed['file_kind'] = file_kind
    parsed['text_source'] = text_source
    parsed['warnings'] = warnings + parsed.get('warnings', [])
    parsed['ok'] = bool(parsed.get('fields'))
    n_fields = len(parsed.get('fields', {}))
    if n_fields >= 3:
        parsed['message'] = f'اطلاعات فاکتور خوانده شد ({n_fields} فیلد تشخیص داده شد).'
    elif n_fields > 0:
        parsed['message'] = f'{n_fields} فیلد از فاکتور استخراج شد. بقیه را دستی وارد کنید.'
    else:
        parsed['message'] = 'متن فایل خوانده شد اما فیلدی تشخیص داده نشد. اطلاعات را دستی وارد کنید.'
    return parsed


def extract_pdf_text_or_ocr(file_path):
    warnings = []
    text = ''
    try:
        import fitz

        with fitz.open(file_path) as doc:
            text = '\n'.join(page.get_text('text') or '' for page in doc)
            if normalize_text(text).strip():
                return text, 'pymupdf_text', warnings

            page_texts = []
            for page_index, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                    temp.write(pix.tobytes('png'))
                    temp_path = temp.name
                try:
                    page_text, _source, page_warnings = extract_image_text(temp_path)
                    warnings.extend([f'صفحه {page_index + 1}: {w}' for w in page_warnings])
                    page_texts.append(page_text)
                finally:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
            return '\n'.join(page_texts), 'paddleocr_pdf', warnings
    except ImportError:
        warnings.append('PyMuPDF نصب نیست؛ تلاش با pypdf.')
    except Exception as exc:
        warnings.append(f'خواندن PDF با PyMuPDF: {exc}')

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
        warnings.append(f'خواندن PDF با pypdf: {exc}')

    warnings.append('متن قابل استخراج از PDF پیدا نشد.')
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
            image, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 11,
        )
        temp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp.close()
        cv2.imwrite(temp.name, image)
        return temp.name, temp.name, []
    except ImportError:
        return file_path, '', ['OpenCV نصب نیست.']
    except Exception as exc:
        return file_path, '', [f'پیش‌پردازش تصویر: {exc}']


def paddle_ocr_image(file_path):
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return '', ['PaddleOCR نصب نیست؛ OCR عکس امکان‌پذیر نیست.']
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
        return '', [f'PaddleOCR: {exc}']


_PADDLE_OCR = None


def get_paddle_ocr():
    global _PADDLE_OCR
    if _PADDLE_OCR is None:
        from paddleocr import PaddleOCR

        model_dirs = _paddle_ocr_model_dirs()
        if not model_dirs:
            raise RuntimeError(
                'PaddleOCR: مسیر مدل‌ها پیدا نشد. '
                'PADDLEOCR_DET_MODEL_DIR و PADDLEOCR_REC_MODEL_DIR را تنظیم کنید.'
            )
        kwargs = {
            'lang': 'fa',
            'show_log': False,
            'det_model_dir': str(model_dirs['det']),
            'rec_model_dir': str(model_dirs['rec']),
            'use_angle_cls': bool(model_dirs.get('cls')),
        }
        if model_dirs.get('cls'):
            kwargs['cls_model_dir'] = str(model_dirs['cls'])
        _PADDLE_OCR = PaddleOCR(**kwargs)
    return _PADDLE_OCR


def _paddle_ocr_model_dirs():
    base_dir = Path(getattr(settings, 'PADDLEOCR_MODEL_DIR', '') or '')
    det_dir = Path(getattr(settings, 'PADDLEOCR_DET_MODEL_DIR', '') or (base_dir / 'det' if base_dir else ''))
    rec_dir = Path(getattr(settings, 'PADDLEOCR_REC_MODEL_DIR', '') or (base_dir / 'rec' if base_dir else ''))
    cls_dir = Path(getattr(settings, 'PADDLEOCR_CLS_MODEL_DIR', '') or (base_dir / 'cls' if base_dir else ''))
    if not _model_dir_ready(det_dir) or not _model_dir_ready(rec_dir):
        return None
    result = {'det': det_dir, 'rec': rec_dir}
    if _model_dir_ready(cls_dir):
        result['cls'] = cls_dir
    return result


def _model_dir_ready(path):
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except OSError:
        return False


# ─── ابزارهای کمکی استخراج ─────────────────────────────────────────────────

def _search_after_label(text, labels, max_chars=80):
    """
    جستجو برای مقدار بعد از یک لیبل.
    دو حالت پشتیبانی می‌شود:
    ۱. مقدار در همان خط لیبل
    ۲. مقدار در خط بعد (رایج در فاکتورهای فارسی)
    """
    for label in labels:
        # حالت ۱: همان خط
        pattern = rf'(?:{label})\s*[:：\-]?\s*([^\n]{{1,{max_chars}}})'
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip(' :：-،')
            if value:
                return value
        # حالت ۲: خط بعدی (مقدار در سطر جداگانه)
        pattern2 = rf'(?:{label})\s*[:：\-]?\s*\n\s*([^\n]{{1,{max_chars}}})'
        m2 = re.search(pattern2, text, flags=re.IGNORECASE)
        if m2:
            value2 = m2.group(1).strip(' :：-،')
            if value2:
                return value2
    return ''


def _extract_number_from(text):
    """استخراج اولین عدد معنادار از یک رشته."""
    nums = re.findall(r'[\d,\s]+', normalize_digits(text or ''))
    for n in nums:
        digits = re.sub(r'\D', '', n)
        if len(digits) >= 3:
            return digits
    return ''


# ─── استخراج شماره فاکتور ──────────────────────────────────────────────────

def _extract_invoice_number(text):
    """استخراج دقیق مقدار شماره فاکتور."""
    invoice_labels = [
        r'شماره\s*فاکتور',
        r'شماره\s*صورت\s*حساب',
        r'شماره\s*صورتحساب',
        r'فاکتور\s*(?:شماره|#|no\.?)',
        r'شماره\s*پیش\s*فاکتور',
        r'invoice\s*(?:no\.?|number|#)',
        r'شناسه\s*فاکتور',
        r'کد\s*فاکتور',
        r'شماره\s*سند',
        r'سریال\s*فاکتور',
        r'شماره\s*رسید',
        r'No\s*فاکتور',
        r'شماره\s*:',    # "شماره:" به‌تنهایی (رایج در فاکتورهای فارسی)
    ]
    for label in invoice_labels:
        # همان خط: لیبل + عدد/کد
        pattern = rf'(?:{label})\s*[:：\-#]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{{0,20}})'
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if re.search(r'\d', val):
                return _clean_short_value(re.split(r'\s{2,}|\t|\n', val)[0].strip())

        # خط بعدی: لیبل در یک خط، عدد در خط بعد
        pattern2 = rf'(?:{label})\s*[:：\-#]?\s*\n\s*([A-Za-z0-9][A-Za-z0-9\-/\s]{{0,25}})'
        m2 = re.search(pattern2, text, flags=re.IGNORECASE)
        if m2:
            val2 = m2.group(1).strip()
            if re.search(r'\d', val2):
                # فقط اولین کلمه/عدد
                first_token = re.split(r'\s+', val2)[0].strip()
                if first_token:
                    return _clean_short_value(first_token)

    # الگوهای کلاسیک
    for pat in [r'\b(?:INV|FA|FACT|FTR|FAK)[\-/]?[A-Z0-9\-/]{2,15}\b']:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return _clean_short_value(m.group(0))
    return ''


# ─── استخراج شماره حواله / مرجع ────────────────────────────────────────────

def _extract_reference_number(text):
    labels = [
        r'شماره\s*حواله',
        r'شماره\s*ارجاع',
        r'شماره\s*مرجع',
        r'کد\s*رهگیری',
        r'شماره\s*پیگیری',
        r'شناسه\s*پرداخت',
        r'شماره\s*تراکنش',
        r'کد\s*تراکنش',
        r'reference\s*(?:no|number)',
        r'tracking\s*(?:no|code)',
        r'شماره\s*(?:دستور|پرداخت)',
        r'کد\s*مرجع',
        r'کد\s*پیگیری',
    ]
    value = _search_after_label(text, labels)
    return _clean_short_value(value)


# ─── استخراج مبلغ ──────────────────────────────────────────────────────────

def _extract_amount(text):
    """
    استخراج مبلغ کل فاکتور با اولویت‌بندی دقیق:
    ۱. لیبل مبلغ کل/قابل پرداخت مستقیم (بالاترین اولویت)
    ۲. خطوط با کلمه کل/جمع + ریال/تومان
    ۳. bزرگ‌ترین عدد ریالی (fallback)
    """

    # ─── اولویت ۱: لیبل‌های صریح مبلغ کل ─────────────────────────────
    # اول دقیق‌ترین لیبل‌ها
    priority_labels = [
        r'مبلغ\s*کل',
        r'جمع\s*کل',
        r'مبلغ\s*قابل\s*پرداخت',
        r'قابل\s*پرداخت',
        r'مبلغ\s*نهایی',
        r'جمع\s*نهایی',
        r'مجموع\s*کل',
        r'مانده\s*قابل\s*پرداخت',
        r'مبلغ\s*بدهکار',
        r'grand\s*total',
        r'total\s*payable',
        r'total\s*amount',
        r'amount\s*due',
        r'مبلغ\s*(?:واجب\s*الدفع|پرداختنی)',
        r'جمع\s*فاکتور',
        r'مبلغ\s*فاکتور',
        r'مبلغ\s*صورتحساب',
        r'جمع\s*صورتحساب',
        r'مبلغ\s*کل\s*(?:با|بدون|شامل)\s*مالیات',
        r'net\s*(?:amount|total)',
    ]

    for label in priority_labels:
        # حالت ۱: عدد بعد از لیبل (LTR / logical order)
        pattern = rf'(?:{label})\s*[:：\-]?\s*([0-9][0-9,،\s.]{{2,30}})'
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) >= 3:
                return digits

        # حالت ۲: عدد قبل از لیبل (RTL visual order — رایج در PDFهای فارسی)
        pattern_rtl = rf'([0-9][0-9,،\s.]{{2,30}})\s*(?:{label})'
        m2 = re.search(pattern_rtl, text, flags=re.IGNORECASE)
        if m2:
            digits = re.sub(r'\D', '', m2.group(1))
            if len(digits) >= 5:
                return digits

        # حالت ۳: لیبل در خط جداگانه، عدد در خط بعد
        pattern_nl = rf'(?:{label})\s*[:：\-]?\s*\n\s*([0-9][0-9,،\s.]{{2,20}})'
        m3 = re.search(pattern_nl, text, flags=re.IGNORECASE)
        if m3:
            digits = re.sub(r'\D', '', m3.group(1))
            if len(digits) >= 3:
                return digits

    # ─── اولویت ۲: خط حاوی هم «کل/جمع/نهایی» و هم «ریال/تومان» ──────
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        has_currency = bool(re.search(r'ریال|تومان|rial|irr', ln, flags=re.IGNORECASE))
        has_total_kw = bool(re.search(
            r'کل|جمع|قابل\s*پرداخت|مانده|نهایی|بدهکار|total|grand|payable|net',
            ln, flags=re.IGNORECASE
        ))
        if has_currency and has_total_kw:
            nums = [
                int(re.sub(r'\D', '', m.group(1)))
                for m in re.finditer(r'(?<!\d)([0-9]{1,3}(?:[,\s][0-9]{3})+|[0-9]{5,})(?!\d)', ln)
                if re.sub(r'\D', '', m.group(1))
            ]
            if nums:
                return str(max(nums))

    # ─── اولویت ۳: بزرگ‌ترین عدد ریالی (fallback) ─────────────────────
    currency_nums = []
    for line in text.splitlines():
        if re.search(r'ریال|تومان|rial|irr', line, flags=re.IGNORECASE):
            for m in re.finditer(r'(?<!\d)([0-9]{1,3}(?:[,\s][0-9]{3})+|[0-9]{6,})(?!\d)', line):
                digits = re.sub(r'\D', '', m.group(1))
                if digits:
                    currency_nums.append(int(digits))
    if currency_nums:
        return str(max(currency_nums))

    return ''


# ─── استخراج تاریخ ─────────────────────────────────────────────────────────

def _extract_invoice_date(text):
    date_labels = [
        r'تاریخ\s*فاکتور',
        r'تاریخ\s*صورت(?:\s*حساب|حساب)',
        r'تاریخ\s*صدور',
        r'تاریخ\s*سند',
        r'تاریخ\s*رسید',
        r'تاریخ\s*پیش\s*فاکتور',
        r'invoice\s*date',
        r'date\s*(?:of\s*)?(?:invoice|issue)',
        r'تاریخ',
    ]
    # ابتدا بعد از لیبل‌ها
    label_value = _search_after_label(text, date_labels[:-1], max_chars=40)
    date_text = _find_date_in(label_value) or _find_date_in(text)
    if not date_text:
        return ''
    return _parse_date_to_jalali(date_text)


def _find_date_in(text):
    """پیدا کردن الگوی تاریخ در متن — با پشتیبانی از فرمت‌های بیشتر."""
    patterns = [
        r'(?<!\d)(\d{4}[\/\-.]\d{1,2}[\/\-.]\d{1,2})(?!\d)',   # YYYY/MM/DD
        r'(?<!\d)(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{4})(?!\d)',   # DD/MM/YYYY
        r'(?<!\d)(\d{2}[\/\-.]\d{1,2}[\/\-.]\d{1,2})(?!\d)',   # YY/MM/DD
    ]
    for pat in patterns:
        m = re.search(pat, text or '')
        if m:
            return m.group(1)
    return ''


def _parse_date_to_jalali(date_text):
    try:
        import jdatetime
    except ImportError:
        return date_text

    parts_raw = re.split(r'[\/\-.]', date_text)
    if len(parts_raw) != 3:
        return ''
    try:
        parts = [int(p) for p in parts_raw]
    except ValueError:
        return ''

    # تشخیص ترتیب: اگر اولین عدد > 31 → YYYY/MM/DD
    if parts[0] > 31:
        year, month, day = parts
    elif parts[2] > 31:
        # DD/MM/YYYY
        day, month, year = parts
    else:
        year, month, day = parts

    if year < 100:
        year += 1400 if year < 50 else 1300

    # میلادی → شمسی
    if year > 1800:
        try:
            return jdatetime.date.fromgregorian(year=year, month=month, day=day).strftime('%Y/%m/%d')
        except (ValueError, Exception):
            return ''

    # شمسی
    try:
        return jdatetime.date(year, month, day).strftime('%Y/%m/%d')
    except (ValueError, Exception):
        return ''


# ─── استخراج نام خریدار/مشتری ─────────────────────────────────────────────

def _extract_customer_name(text):
    """استخراج نام خریدار از فاکتور."""
    buyer_labels = [
        r'نام\s*خریدار',
        r'خریدار\s*(?:محترم)?',
        r'نام\s*مشتری',
        r'مشتری',
        r'طرف\s*حساب',
        r'فروخته\s*شده\s*به',
        r'تحویل\s*به',
        r'گیرنده',
        r'buyer|customer|client|bill\s*to|sold\s*to',
        r'نام\s*و\s*نام\s*خانوادگی\s*خریدار',
        r'شرکت\s*خریدار',
        r'نام\s*شرکت\s*(?:خریدار|مشتری)',
        r'به\s*نام',
    ]
    for label in buyer_labels:
        pattern = rf'(?:{label})\s*[:：\-]?\s*([^\n\d]{{2,60}})'
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            val = m.group(1).strip(' :：-،,')
            # حذف کلمات اضافه آخر
            val = re.split(r'\s{2,}|\t', val)[0].strip()
            if len(val) >= 2 and not re.match(r'^\d+$', val):
                return _clean_short_value(val)
    return ''


# ─── استخراج نام فروشنده (اختیاری) ────────────────────────────────────────

def _extract_vendor_name(text):
    """استخراج نام فروشنده — فقط اگر لیبل صریح وجود داشته باشد."""
    labels = [
        r'نام\s*(?:شرکت|فروشنده|صادرکننده|فروش)',
        r'فروشنده\s*[:：]',
        r'صادرکننده\s*[:：]',
        r'شرکت\s*فروشنده',
        r'seller\s*[:：]',
        r'vendor\s*[:：]',
        r'supplier\s*[:：]',
        r'issued\s*by\s*[:：]',
    ]
    value = _search_after_label(text, labels, max_chars=60)
    if value:
        cleaned = _clean_short_value(value)
        # رد کردن مقادیر نامعتبر (لیبل‌های دیگر)
        invalid = {'امضاء', 'signature', 'مهر', 'تاریخ', 'شماره', 'تلفن'}
        if not any(inv in cleaned for inv in invalid):
            return cleaned
    return ''


# ─── استخراج مالیات ────────────────────────────────────────────────────────

def _extract_tax_amount(text):
    labels = [
        r'مالیات\s*(?:بر\s*ارزش\s*افزوده)?',
        r'ارزش\s*افزوده',
        r'VAT|tax',
        r'مالیات\s*کل',
    ]
    for label in labels:
        pattern = rf'(?:{label})[^\d\n]{{0,40}}([0-9][\d,\s.]{{2,}})'
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) >= 2:
                return digits
    return ''


# ─── تجمیع پارسر ───────────────────────────────────────────────────────────

def parse_invoice_text(text):
    """استخراج تمام فیلدهای فاکتور از متن نرمال‌شده."""
    raw_fields = {
        'invoice_number':   _extract_invoice_number(text),
        'reference_number': _extract_reference_number(text),
        'amount':           _extract_amount(text),
        'invoice_date':     _extract_invoice_date(text),
        'customer_name':    _extract_customer_name(text),
        'vendor_name':      _extract_vendor_name(text),
        'tax_amount':       _extract_tax_amount(text),
    }

    # confidence بر اساس اینکه بعد از لیبل آمده یا heuristic
    label_based = {'invoice_number', 'invoice_date', 'reference_number', 'customer_name', 'vendor_name', 'tax_amount'}
    fields = {}
    for key, value in raw_fields.items():
        if not value:
            continue
        confidence = 0.85 if key in label_based else 0.70
        fields[key] = {'value': value, 'confidence': confidence, 'source': 'parser'}

    return {'fields': fields, 'warnings': []}


def flatten_fields(result):
    fields = result.get('fields') or {}
    return {
        key: value.get('value') if isinstance(value, dict) else value
        for key, value in fields.items()
        if value
    }


# ─── ابزار تمیزسازی ─────────────────────────────────────────────────────────

def _clean_short_value(value):
    value = normalize_digits(str(value or ''))
    # برش بعد از whitespace چندگانه یا newline
    value = re.split(r'\s{2,}|\t|\n', value)[0]
    value = value.strip(' :：-،,')
    return value[:100]
