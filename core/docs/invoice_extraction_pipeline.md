# Invoice Extraction Pipeline

معماری خواندن فاکتور:

```text
Django API
|
InvoiceExtractionJob در DB
|
پردازش inline در Django
|
OCR Worker
|
PyMuPDF / PaddleOCR / OpenCV
|
Regex + Parser
|
JSON Result در DB
|
UI Suggestions
```

## نصب وابستگی‌های OCR

وابستگی‌های اصلی برنامه در `requirements.txt` هستند. وابستگی‌های سنگین OCR در فایل جدا قرار گرفته‌اند:

```powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements-ocr.txt
```

روی محیط آفلاین باید برای `requirements-ocr.txt` هم wheelhouse جدا ساخته شود.

## پردازش فعلی

در مرحله فعلی Redis پیاده‌سازی نشده است. خواندن preview همان لحظه در Django انجام می‌شود، اما نتیجه هر پردازش در `InvoiceExtractionJob` ذخیره می‌شود.

برای پردازش Jobهای باقی‌مانده در DB:

```powershell
.\venv\Scripts\python.exe manage.py process_invoice_extractions --limit 20
```

Redis/RQ در مرحله بعد، بعد از تست واقعی OCR، به همین لایه Job اضافه می‌شود.

## خروجی JSON

هر پردازش در `InvoiceExtractionJob.result_json` ذخیره می‌شود:

```json
{
  "fields": {
    "invoice_number": {"value": "INV-1001", "confidence": 0.8, "source": "parser"},
    "amount": {"value": "2500000", "confidence": 0.8, "source": "parser"}
  },
  "raw_text_preview": "...",
  "file_kind": "pdf",
  "text_source": "pymupdf_text",
  "warnings": []
}
```

هیچ مقدار استخراج‌شده‌ای مستقیم در فرم ثبت نمی‌شود؛ UI فقط پیشنهادها را نشان می‌دهد و کاربر باید هر فیلد را جداگانه اعمال کند.
