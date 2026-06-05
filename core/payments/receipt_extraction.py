"""
استخراج اطلاعات فیش‌های بانکی ایرانی
اولویت: Claude Vision API → Tesseract → PaddleOCR → EasyOCR
بر اساس نمونه‌های واقعی بانک ملی (BAM)، سامان (موبایلت)، ملت و ATM
"""

import os as _os
import re
from pathlib import Path as _Path
from .invoice_extraction import (
    normalize_text,
    detect_file_kind,
    extract_pdf_text_or_ocr,
    preprocess_image,
)

_TESSERACT_CMD   = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
_TESSDATA_PREFIX = str(_Path(__file__).resolve().parent.parent / 'tessdata')
_RECEIPT_OCR     = None

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

# جداکننده‌های رایج فارسی در اعداد
_SEP = r'[,،٬\s\.،]'

IRANIAN_BANKS = {
    'ملی': ['بانک ملی', 'bank melli', 'bmi', 'baam'],
    'ملت': ['بانک ملت', 'bank mellat', 'بانك ملت'],
    'سامان': ['بانک سامان', 'saman bank', 'saman'],
    'صادرات': ['بانک صادرات', 'bank saderat'],
    'تجارت': ['بانک تجارت', 'bank tejarat'],
    'پارسیان': ['بانک پارسیان', 'parsian', 'bank parsian'],
    'پاسارگاد': ['بانک پاسارگاد', 'pasargad'],
    'کشاورزی': ['بانک کشاورزی', 'keshavarzi'],
    'مسکن': ['بانک مسکن', 'maskan'],
    'رفاه': ['بانک رفاه', 'refah'],
    'اقتصاد نوین': ['اقتصاد نوین', 'eghtesad novin'],
    'سینا': ['بانک سینا', 'sina'],
    'شهر': ['بانک شهر', 'shahr'],
    'دی': ['بانک دی'],
    'آینده': ['بانک آینده', 'ayandeh'],
    'قرض الحسنه مهر': ['مهر ایران', 'mehr iran'],
    'پست بانک': ['پست بانک', 'post bank'],
}

# پیشوند کارت‌های بانکی ایرانی (۶ رقم اول)
CARD_BIN_MAP = {
    '603799': 'ملی', '603769': 'ملی',
    '610433': 'ملت', '991975': 'ملت', '603770': 'ملت', '606373': 'ملت',
    '621986': 'سامان', '639607': 'سامان',
    '603769': 'ملی', '627648': 'کشاورزی',
    '627961': 'صنعت و معدن', '603770': 'ملت',
    '505785': 'ایران زمین', '502229': 'پاسارگاد',
    '639599': 'قوامین', '504172': 'اقتصاد نوین',
    '627412': 'اقتصاد نوین', '627884': 'پارسیان',
    '622106': 'پارسیان', '502806': 'شهر',
    '639347': 'پاسارگاد', '502938': 'دی',
    '603769': 'ملی', '589210': 'سپه',
    '627381': 'انصار', '603799': 'ملی',
}


def _norm(text):
    """نرمال‌سازی اعداد فارسی به انگلیسی."""
    return str(text or '').translate(PERSIAN_DIGITS)


def _clean_number(raw):
    """حذف جداکننده‌ها و برگرداندن عدد خالص."""
    return re.sub(r'[,،٬\s\.]', '', _norm(raw))


# ─── OCR ──────────────────────────────────────────────────────────────────────

def _crop_white_card(arr):
    """
    تشخیص و برش ناحیه کارت سفید داخل فیش —
    فیش‌های بانک ملی (BAM) پس‌زمینه نارنجی دارند،
    داده اصلی در کارت سفید مرکزی است.
    """
    import numpy as np
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    white = (r > 220) & (g > 220) & (b > 220)
    rows = np.where(white.any(axis=1))[0]
    cols = np.where(white.any(axis=0))[0]
    if len(rows) < 10 or len(cols) < 10:
        return arr
    r0, r1 = rows[0], rows[-1]
    c0, c1 = cols[0], cols[-1]
    h, w = arr.shape[:2]
    # حداقل ۳۰٪ تصویر باشد
    if (r1 - r0) < h * 0.3 or (c1 - c0) < w * 0.3:
        return arr
    # کمی حاشیه اضافه
    pad = 10
    return arr[max(0, r0-pad):min(h, r1+pad),
               max(0, c0-pad):min(w, c1+pad)]


def _preprocess_receipt_image(file_path):
    """
    پیش‌پردازش اختصاصی فیش بانکی:
    - حذف پس‌زمینه رنگی (نارنجی، سبز، تیره)
    - استخراج ناحیه سفید کارت
    - contrast بالا برای خوانایی OCR
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        import numpy as np

        img = Image.open(file_path).convert('RGB')
        arr = np.array(img)

        # ۱. برش کارت سفید (حذف پس‌زمینه نارنجی/تیره)
        arr = _crop_white_card(arr)
        img = Image.fromarray(arr)

        # ۲. upscale
        w, h = img.size
        if w < 1600:
            scale = max(2, 1600 // w)
            img = img.resize((w * scale, h * scale), Image.LANCZOS)

        # ۳. grayscale
        gray = img.convert('L')

        # ۴. بهبود کنتراست و وضوح
        gray = ImageEnhance.Contrast(gray).enhance(3.0)
        gray = ImageEnhance.Sharpness(gray).enhance(2.5)

        # ۵. حذف نویز با فیلتر
        gray = gray.filter(ImageFilter.MedianFilter(size=3))

        # ۶. binarize — تبدیل به سیاه/سفید
        import numpy as np
        g_arr = np.array(gray)
        # threshold اتسو
        threshold = int(np.percentile(g_arr, 30))
        threshold = max(100, min(200, threshold))
        bw = (g_arr > threshold).astype('uint8') * 255
        result = Image.fromarray(bw)

        return result
    except Exception as e:
        # fallback ساده
        from PIL import Image, ImageEnhance
        img = Image.open(file_path).convert('L')
        w, h = img.size
        if w < 1400:
            img = img.resize((w * 2, h * 2), Image.LANCZOS)
        return ImageEnhance.Contrast(img).enhance(2.0)


def _extract_image_text_receipt(file_path):
    """
    استخراج متن — اولویت: Tesseract (با preprocessing) → PaddleOCR → EasyOCR
    """
    warnings = []

    # ── ۱. Tesseract با preprocessing بهینه ─────────────────────
    if _os.path.exists(_TESSERACT_CMD):
        try:
            import pytesseract, tempfile

            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
            _os.environ['TESSDATA_PREFIX'] = _TESSDATA_PREFIX

            # پیش‌پردازش
            processed = _preprocess_receipt_image(file_path)

            # ذخیره موقت
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            processed.save(tmp.name, 'PNG')
            tmp.close()

            best_text = ''
            for psm in ['6', '4', '3']:
                cfg = f'--oem 3 --psm {psm} -c preserve_interword_spaces=1'
                t = pytesseract.image_to_string(
                    processed, lang='fas+eng', config=cfg)
                if len(t) > len(best_text):
                    best_text = t

            try:
                _os.unlink(tmp.name)
            except Exception:
                pass

            if best_text.strip():
                return best_text, 'tesseract', warnings
            warnings.append('Tesseract: متنی شناسایی نشد.')
        except Exception as exc:
            warnings.append(f'Tesseract: {exc}')

    # ── ۲. PaddleOCR ─────────────────────────────────────────────
    try:
        from paddleocr import PaddleOCR
        global _RECEIPT_OCR
        if _RECEIPT_OCR is None:
            _RECEIPT_OCR = PaddleOCR(
                lang='fa', show_log=False,
                use_angle_cls=True, use_mkldnn=False, use_gpu=False,
            )
        result = _RECEIPT_OCR.ocr(file_path, cls=True)
        lines = [item[1][0] for page in (result or [])
                 for item in (page or []) if item and len(item) > 1]
        text = '\n'.join(lines)
        if text.strip():
            return text, 'paddleocr', warnings
    except Exception as exc:
        warnings.append(f'PaddleOCR: {exc}')

    # ── ۳. EasyOCR ───────────────────────────────────────────────
    try:
        import easyocr
        reader = easyocr.Reader(['fa', 'en'], gpu=False, verbose=False)
        result = reader.readtext(file_path, detail=0)
        text = '\n'.join(str(r) for r in result)
        if text.strip():
            return text, 'easyocr', warnings
    except Exception as exc:
        warnings.append(f'EasyOCR: {exc}')

    return '', 'none', warnings


# ─── پارسر اصلی ───────────────────────────────────────────────────────────────

def _search_label(text, labels, max_chars=60):
    """مقدار بعد از label را پیدا می‌کند (همان خط یا خط بعد)."""
    for label in labels:
        # همان خط: label : value
        pat = rf'(?:{label})\s*[:\-]?\s*(.{{2,{max_chars}}}?)(?:\n|$)'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                return val
        # label در انتهای خط، مقدار در خط قبل (RTL)
        pat2 = rf'(.{{2,{max_chars}}}?)\s*{label}'
        m2 = re.search(pat2, text, re.IGNORECASE)
        if m2:
            val = m2.group(1).strip()
            if val and len(val) > 1:
                return val
    return ''


def _extract_amount(text):
    """مبلغ — فرمت‌های مختلف: ۲۰۰,۰۰۰,۰۰۰ ریال یا ۲۰٬۰۰۰٬۰۰۰"""
    # label محور
    amount_labels = [
        r'مبلغ\s*(?:انتقال|واریز|پرداخت|تراکنش)?',
        r'مقدار',
        r'مبلغ\s*(?:ریال|تومان)?',
        r'amount',
    ]
    for label in amount_labels:
        pat = rf'(?:{label})\s*[:\-]?\s*([۰-۹\d][۰-۹\d,،٬\s\.]+(?:ریال|تومان)?)'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = _clean_number(m.group(1).replace('ریال', '').replace('تومان', ''))
            if len(raw) >= 4:
                return raw

    # قبل از «ریال» یا «تومان»
    m = re.search(r'([۰-۹\d][۰-۹\d,،٬\s\.]{3,})\s*(?:ریال|تومان)', text)
    if m:
        raw = _clean_number(m.group(1))
        if len(raw) >= 4:
            return raw

    # بزرگ‌ترین عدد ≥ ۶ رقم
    nums = re.findall(r'[۰-۹\d]{1,3}(?:[,،٬][۰-۹\d]{3})+', text)
    if nums:
        candidates = [int(_clean_number(n)) for n in nums if len(_clean_number(n)) >= 6]
        if candidates:
            return str(max(candidates))
    return ''


def _extract_tracking(text):
    """شماره پیگیری / کد پیگیری / شماره ارجاع / شماره مرجع بانک"""
    labels = [
        r'شماره\s*پیگیری',
        r'کد\s*پیگیری',
        r'شماره\s*ارجاع',
        r'شماره\s*مرجع\s*(?:بانک)?',
        r'شماره\s*رهگیری',
        r'کد\s*رهگیری',
        r'reference\s*(?:number|no|id)?',
        r'trace\s*(?:id|no)?',
        r'rrn',
    ]
    for label in labels:
        pat = rf'(?:{label})\s*[:\-]?\s*([۰-۹\dA-Za-z][\w\-]{{4,24}})'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _norm(m.group(1).strip())
            if re.search(r'\d{5,}', val):
                return val

    # عدد ۶ تا ۲۴ رقمی که پیگیری باشد
    candidates = re.findall(r'\b(\d{6,24})\b', _norm(text))
    for c in candidates:
        if 6 <= len(c) <= 24 and not c.startswith('14') and not c.startswith('13'):
            return c
    return ''


def _extract_card_or_account(text, direction='dst'):
    """
    استخراج شماره کارت یا حساب مبدا/مقصد.
    direction: 'src' | 'dst'
    """
    if direction == 'src':
        labels = [
            r'(?:شماره\s*)?(?:کارت|حساب|سپرده)\s*مبد[اأ]',
            r'از\s*(?:کارت|حساب)',
            r'از\s*کارت',
            r'کارت\s*مبد[اأ]',
            r'حساب\s*مبد[اأ]',
            r'سپرده\s*مبد[اأ]',
        ]
    else:
        labels = [
            r'(?:شماره\s*)?(?:کارت|حساب|سپرده)\s*مقصد',
            r'به\s*(?:کارت|حساب)',
            r'به\s*کارت',
            r'کارت\s*مقصد',
            r'حساب\s*مقصد',
        ]

    # regex شماره‌های معتبر
    ACCT_RE = re.compile(
        r'(?:'
        r'IR\d{24}'                          # IBAN
        r'|\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}'  # کارت ۱۶ رقم
        r'|[\d\*X]{4}[-_]?[\d\*X]{4}[-_]?[\d\*X]{4}[-_]?[\d\*X]{4}'  # با ستاره
        r'|\d{10,16}'                        # حساب ۱۰-۱۶ رقم
        r'|\d{3}-\d{2}-\d{7,8}-\d'          # فرمت حساب سامان
        r')',
        re.IGNORECASE
    )

    for label in labels:
        pat = rf'(?:{label})\s*[:\-]?\s*([^\n]{{5,35}})'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _norm(m.group(1).strip())
            am = ACCT_RE.search(val)
            if am:
                return am.group(0)

    # همه شماره‌های کارت/حساب را پیدا کن و اولی/دومی را برگردان
    ntext = _norm(text)
    all_nums = []
    for m in ACCT_RE.finditer(ntext):
        v = m.group(0)
        if len(re.sub(r'[^\d]', '', v)) >= 10:
            all_nums.append(v)

    all_nums = list(dict.fromkeys(all_nums))
    if direction == 'src' and len(all_nums) >= 1:
        return all_nums[0]
    if direction == 'dst' and len(all_nums) >= 2:
        return all_nums[1]
    if direction == 'dst' and len(all_nums) == 1:
        return all_nums[0]
    return ''


def _extract_dest_owner(text):
    """نام صاحب حساب/کارت مقصد."""
    labels = [
        r'متعلق\s*به',
        r'به\s*نام',
        r'بنام',
        r'(?:نام\s*)?گیرنده',
        r'دریافت\s*(?:کننده)?',
        r'(?:نام\s*)?(?:صاحب|دارنده)\s*(?:حساب|کارت)?',
        r'account\s*(?:holder|owner|name)',
        r'beneficiary\s*name',
    ]
    for label in labels:
        pat = rf'(?:{label})\s*[:\-]?\s*([^\n\d]{{2,40}})'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip(' :،-')
            val = re.split(r'\s{2,}|\t|\n', val)[0].strip()
            val = re.sub(r'[^؀-ۿa-zA-Z\s]', '', val).strip()
            if len(val) >= 2:
                return val[:50]

    # دریافت کننده در سطر جداگانه
    m = re.search(r'دریافت\s*کننده\s*\n([^\n\d]{2,40})', text)
    if m:
        return m.group(1).strip()[:50]
    return ''


def _extract_src_owner(text):
    """نام انتقال‌دهنده / صاحب حساب مبدا."""
    labels = [
        r'انتقال\s*(?:دهنده)?',
        r'از\s*(?:نام|طرف)?',
        r'(?:نام\s*)?فرستنده',
        r'(?:نام\s*)?پرداخت\s*(?:کننده)?',
    ]
    for label in labels:
        pat = rf'(?:{label})\s*[:\-]?\s*([^\n\d]{{2,40}})'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip(' :،-')
            val = re.split(r'\s{2,}|\t|\n', val)[0].strip()
            val = re.sub(r'[^؀-ۿa-zA-Z\s]', '', val).strip()
            if len(val) >= 2:
                return val[:50]
    return ''


def _detect_bank_from_text(text):
    """تشخیص نام بانک از متن."""
    t = text.lower()
    for bank_name, keywords in IRANIAN_BANKS.items():
        for kw in keywords:
            if kw.lower() in t:
                return bank_name
    return ''


def _detect_bank_from_card(card_number):
    """تشخیص بانک از ۶ رقم اول کارت."""
    digits = re.sub(r'[^\d]', '', card_number or '')
    if len(digits) >= 6:
        bin6 = digits[:6]
        return CARD_BIN_MAP.get(bin6, '')
    return ''


def _extract_date(text):
    """تاریخ تراکنش."""
    labels = [r'تاریخ(?:\s*و\s*زمان)?', r'زمان(?:\s*انتقال)?', r'date', r'time']
    for label in labels:
        pat = rf'(?:{label})\s*[:\-]?\s*([^\n]{{6,30}})'
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _norm(m.group(1).strip())
            if re.search(r'\d{4}', val):
                return val[:30]

    # جستجو مستقیم: ۱۴۰۳/۰۶/۲۰
    m = re.search(r'(?<!\d)(1[34]\d{2}[/\-.]\d{1,2}[/\-.]\d{1,2})(?!\d)', _norm(text))
    if m:
        return m.group(1)
    return ''


def _extract_transaction_type(text):
    """نوع تراکنش."""
    patterns = [
        r'کارت\s*به\s*کارت',
        r'انتقال\s*(?:وجه\s*)?(?:بین\s*بانکی|پایا|ساتنا)',
        r'انتقال\s*پول',
        r'انتقال\s*وجه',
        r'واریز',
        r'card.to.card',
        r'interbank',
        r'paya',
        r'satna',
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return re.search(pat, text, re.IGNORECASE).group(0)
    return ''


# ─── تابع اصلی پارس ────────────────────────────────────────────────────────────

def parse_receipt_text(text):
    """استخراج همه فیلدهای فیش بانکی از متن."""
    amount       = _extract_amount(text)
    tracking     = _extract_tracking(text)
    src_acct     = _extract_card_or_account(text, 'src')
    dst_acct     = _extract_card_or_account(text, 'dst')
    dest_owner   = _extract_dest_owner(text)
    src_owner    = _extract_src_owner(text)
    date         = _extract_date(text)
    tx_type      = _extract_transaction_type(text)

    # بانک مبدا از کارت مبدا یا متن
    src_bank = (_detect_bank_from_card(src_acct) or
                _detect_bank_from_text(text.split('\n')[0] if text else ''))
    # بانک مقصد
    dst_bank_labels = [r'بانک\s*مقصد', r'destination\s*bank', r'receiving\s*bank']
    dst_bank_raw = _search_label(text, dst_bank_labels)
    dst_bank = (_detect_bank_from_text(dst_bank_raw) or
                _detect_bank_from_card(dst_acct) or
                _detect_bank_from_text(text))

    fields = {}
    def add(key, label, value, icon, note=''):
        if value:
            fields[key] = {'label': label, 'value': value, 'icon': icon, 'note': note}

    add('amount',      'مبلغ (ریال)',             _fmt_amount(amount),    '💰')
    add('tracking',    'شماره پیگیری',             tracking,               '🔢')
    add('src_account', 'حساب/کارت مبدا',           _fmt_card(src_acct),    '💳')
    add('dst_account', 'حساب/کارت مقصد',           _fmt_card(dst_acct),    '💳')
    add('src_bank',    'بانک مبدا',                src_bank,               '🏦')
    add('dst_bank',    'بانک مقصد',                dst_bank,               '🏦')
    add('dest_owner',  'نام صاحب حساب مقصد',       dest_owner,             '👤')
    add('src_owner',   'نام انتقال‌دهنده',          src_owner,              '👤')
    add('date',        'تاریخ / زمان تراکنش',      date,                   '📅')
    add('tx_type',     'نوع تراکنش',               tx_type,                '🔄')

    return fields


def _fmt_amount(raw):
    """فرمت خوانا برای مبلغ."""
    if not raw:
        return ''
    try:
        n = int(raw)
        return f'{n:,}'
    except Exception:
        return raw


def _fmt_card(raw):
    """فرمت استاندارد کارت."""
    if not raw:
        return ''
    digits_only = re.sub(r'[^\d\*Xx]', '', raw)
    if len(digits_only) == 16:
        return '-'.join(digits_only[i:i+4] for i in range(0, 16, 4))
    return raw


# ─── Google Gemini Vision (کاملاً رایگان) ────────────────────────────────────────

_GEMINI_PROMPT = """این تصویر یک فیش/رسید بانکی ایرانی است.
اطلاعات زیر را از آن استخراج کن و فقط JSON برگردان (بدون هیچ متن دیگری):

{
  "amount": "مبلغ به ریال — فقط عدد بدون جداکننده",
  "tracking": "شماره پیگیری یا کد ارجاع",
  "src_account": "کارت یا حساب مبدا",
  "dst_account": "کارت یا حساب مقصد یا IBAN",
  "src_bank": "بانک مبدا",
  "dst_bank": "بانک مقصد",
  "dest_owner": "نام صاحب حساب مقصد",
  "src_owner": "نام انتقال‌دهنده",
  "date": "تاریخ و زمان",
  "tx_type": "نوع تراکنش"
}

اگر فیلدی وجود نداشت، مقدار null بگذار. اعداد فارسی را به انگلیسی تبدیل کن."""


def _extract_with_gemini(file_path, original_name=''):
    """Google Gemini Flash — رایگان، دقیق برای فارسی."""
    from django.conf import settings as _s
    api_key = getattr(_s, 'GEMINI_API_KEY', '')
    if not api_key:
        return None, 'GEMINI_API_KEY تنظیم نشده.'
    try:
        import google.generativeai as genai
        import PIL.Image, json

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        img = PIL.Image.open(file_path)
        response = model.generate_content([img, _GEMINI_PROMPT])
        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw).strip()
        data = json.loads(raw)
        return data, ''
    except Exception as e:
        return None, str(e)


# ─── OCR.space API (رایگان) ─────────────────────────────────────────────────────

def _extract_with_ocrspace(file_path, original_name=''):
    """
    OCR.space — سرویس رایگان آنلاین با پشتیبانی از فارسی/عربی.
    کلید رایگان: تنظیم OCRSPACE_API_KEY در .env
    رجیستر رایگان در: https://ocr.space/ocrapi/freekey
    """
    import urllib.request, urllib.parse, json, mimetypes

    from django.conf import settings as _s
    api_key = getattr(_s, 'OCRSPACE_API_KEY', '') or 'helloworld'

    ext = _os.path.splitext(original_name or file_path)[1].lower()
    mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.pdf': 'application/pdf'}
    mime = mime_map.get(ext, 'image/jpeg')

    try:
        with open(file_path, 'rb') as f:
            img_data = f.read()

        import base64
        b64 = base64.b64encode(img_data).decode()
        base64_img = f'data:{mime};base64,{b64}'

        payload = urllib.parse.urlencode({
            'apikey':       api_key,
            'base64Image':  base64_img,
            'language':     'ara',   # Arabic — شامل فارسی هم می‌شود
            'isOverlayRequired': 'false',
            'detectOrientation':  'true',
            'scale':        'true',
            'OCREngine':    '2',     # موتور پیشرفته‌تر
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.ocr.space/parse/image',
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        if result.get('IsErroredOnProcessing'):
            return None, result.get('ErrorMessage', ['خطای ناشناخته'])[0]

        parsed = result.get('ParsedResults', [])
        if parsed:
            text = parsed[0].get('ParsedText', '')
            if text.strip():
                return text, ''
        return None, 'متنی شناسایی نشد.'
    except Exception as e:
        return None, str(e)


# ─── Claude Vision API ──────────────────────────────────────────────────────────

_CLAUDE_PROMPT = """این تصویر یک فیش/رسید بانکی ایرانی است.
اطلاعات زیر را از آن استخراج کن و دقیقاً به فرمت JSON زیر برگردان (بدون توضیح اضافه):

{
  "amount": "مبلغ به ریال (فقط عدد بدون جداکننده)",
  "tracking": "شماره پیگیری یا کد ارجاع",
  "src_account": "شماره کارت یا حساب مبدا (با ستاره اگر پوشیده باشد)",
  "dst_account": "شماره کارت یا حساب مقصد یا IBAN",
  "src_bank": "نام بانک مبدا",
  "dst_bank": "نام بانک مقصد",
  "dest_owner": "نام صاحب حساب/کارت مقصد",
  "src_owner": "نام انتقال‌دهنده",
  "date": "تاریخ و زمان تراکنش",
  "tx_type": "نوع تراکنش (مثلاً کارت‌به‌کارت، پایا، ساتنا)"
}

اگر هر فیلدی در فیش وجود نداشت، مقدار آن را null بگذار.
اعداد فارسی را به انگلیسی تبدیل کن.
فقط JSON برگردان بدون هیچ متن دیگری."""


def _extract_with_claude(file_path, original_name=''):
    """استخراج با Claude Vision API — بالاترین دقت برای فیش فارسی."""
    from django.conf import settings
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        return None, 'ANTHROPIC_API_KEY تنظیم نشده است.'

    import base64, json, mimetypes
    ext = _os.path.splitext(original_name or file_path)[1].lower()
    mime_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.webp': 'image/webp', '.pdf': 'application/pdf',
    }
    media_type = mime_map.get(ext, 'image/jpeg')

    # PDF → اول صفحه را به عنوان تصویر تبدیل کن
    img_path = file_path
    if media_type == 'application/pdf':
        try:
            import fitz
            with fitz.open(file_path) as doc:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp.close()
                pix.save(tmp.name)
                img_path  = tmp.name
                media_type = 'image/png'
        except Exception as e:
            return None, f'تبدیل PDF: {e}'

    try:
        with open(img_path, 'rb') as f:
            img_b64 = base64.standard_b64encode(f.read()).decode()
    except Exception as e:
        return None, f'خواندن فایل: {e}'

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=512,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image', 'source': {
                        'type': 'base64',
                        'media_type': media_type,
                        'data': img_b64,
                    }},
                    {'type': 'text', 'text': _CLAUDE_PROMPT},
                ],
            }],
        )
        raw = msg.content[0].text.strip()
        # حذف ```json ... ``` اگر وجود داشت
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)
        return data, ''
    except Exception as e:
        return None, str(e)
    finally:
        if img_path != file_path:
            try:
                _os.unlink(img_path)
            except Exception:
                pass


def _claude_to_fields(data):
    """تبدیل JSON خروجی Claude به فرمت fields."""
    fields = {}
    mapping = [
        ('amount',      'مبلغ (ریال)',            '💰'),
        ('tracking',    'شماره پیگیری',            '🔢'),
        ('src_account', 'حساب/کارت مبدا',          '💳'),
        ('dst_account', 'حساب/کارت مقصد',          '💳'),
        ('src_bank',    'بانک مبدا',               '🏦'),
        ('dst_bank',    'بانک مقصد',               '🏦'),
        ('dest_owner',  'نام صاحب حساب مقصد',      '👤'),
        ('src_owner',   'نام انتقال‌دهنده',         '👤'),
        ('date',        'تاریخ / زمان تراکنش',     '📅'),
        ('tx_type',     'نوع تراکنش',              '🔄'),
    ]
    for key, label, icon in mapping:
        val = data.get(key)
        if val and str(val).lower() not in ('null', 'none', '', '-'):
            if key == 'amount':
                try:
                    val = f'{int(str(val).replace(",", "")):,}'
                except Exception:
                    pass
            fields[key] = {'label': label, 'value': str(val), 'icon': icon}
    return fields


# ─── تابع اصلی ─────────────────────────────────────────────────────────────────

def extract_receipt_file(file_path, original_name=''):
    """
    OCR + استخراج اطلاعات فیش بانکی.
    اولویت: Claude Vision → OCR+Regex
    """
    file_kind = detect_file_kind(original_name or file_path)
    warnings  = []
    raw_text  = ''
    text_src  = ''
    fields    = {}
    engine    = ''

    from django.conf import settings as _s

    # ── ۱. Google Gemini Flash (رایگان) ───────────────────────────
    if getattr(_s, 'GEMINI_API_KEY', ''):
        gdata, gerr = _extract_with_gemini(file_path, original_name)
        if gdata:
            fields   = _claude_to_fields(gdata)  # همان فرمت
            text_src = 'gemini-flash'
            engine   = 'gemini'
        elif gerr:
            warnings.append(f'Gemini: {gerr}')

    # ── ۲. Claude Vision (پولی) ────────────────────────────────────
    if not fields and getattr(_s, 'ANTHROPIC_API_KEY', ''):
        claude_data, claude_err = _extract_with_claude(file_path, original_name)
        if claude_data:
            fields   = _claude_to_fields(claude_data)
            text_src = 'claude-vision'
            engine   = 'claude'
        elif claude_err:
            warnings.append(f'Claude Vision: {claude_err}')

    # ── ۳. OCR.space (رایگان با ثبت‌نام) ──────────────────────────
    if not fields and getattr(_s, 'OCRSPACE_API_KEY', ''):
        ocrtext, ocrErr = _extract_with_ocrspace(file_path, original_name)
        if ocrtext:
            raw_text   = ocrtext
            text_src   = 'ocr.space'
            normalized = normalize_text(ocrtext)
            fields     = parse_receipt_text(normalized)
        elif ocrErr:
            warnings.append(f'OCR.space: {ocrErr}')

    # ── ۴. Tesseract محلی (همیشه رایگان) ──────────────────────────
    if not fields:
        if file_kind == 'pdf':
            raw_text, text_src, w = extract_pdf_text_or_ocr(file_path)
            warnings.extend(w)
        elif file_kind == 'image':
            raw_text, text_src, w = _extract_image_text_receipt(file_path)
            warnings.extend(w)
        else:
            warnings.append('فرمت پشتیبانی نمی‌شود — فقط JPEG، PNG، PDF.')

        normalized = normalize_text(raw_text)
        fields     = parse_receipt_text(normalized)
        raw_text   = normalized

    n = len(fields)

    if n >= 5:
        msg = f'✅ {n} فیلد استخراج شد.'
        if engine == 'claude':
            msg += ' (Claude Vision)'
    elif n >= 3:
        msg = f'⚠️ {n} فیلد پیدا شد.'
    elif n > 0:
        msg = f'⚠️ فقط {n} فیلد شناسایی شد.'
    else:
        msg = '❌ اطلاعاتی شناسایی نشد.'

    return {
        'fields':      fields,
        'raw_text':    raw_text,
        'file_kind':   file_kind,
        'text_source': text_src,
        'warnings':    warnings,
        'ok':          n >= 3,
        'message':     msg,
    }
