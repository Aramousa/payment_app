# نصب آفلاین روی Ubuntu 22.04

این بسته برای اجرای عملیاتی بدون اینترنت آماده می‌شود. هیچ نصب runtime نباید از اینترنت انجام شود.

## نصب وابستگی‌های اصلی

از ریشه پروژه:

```bash
cd /var/www/visiunapp/core
source ../venv/bin/activate
bash offline_packages/install_offline_linux.sh
```

اگر سرور با Python پیش‌فرض Ubuntu 22.04 یعنی Python 3.10 اجرا می‌شود:

```bash
pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements.txt
```

اگر عمدا Python 3.12 یا 3.13 روی سرور نصب شده است:

```bash
pip install --no-index --find-links=vendor/wheels-linux -r requirements.txt
```

## OCR

OCR اختیاری است و فقط روی سرور/worker مخصوص OCR نصب شود.

```bash
INCLUDE_OCR=1 bash offline_packages/install_offline_linux.sh
```

بسته فعلی OCR برای Linux Python 3.12 آماده شده است. اگر سرور Ubuntu 22.04 با Python 3.10 اجرا می‌شود، باید wheelهای `offline_packages/ocr-wheels` برای cp310 ساخته شوند.

## مدل‌های PaddleOCR

PaddleOCR علاوه بر wheelهای Python به مدل‌های محلی نیاز دارد. این مدل‌ها باید قبل از انتقال به سرور آفلاین داخل مسیر زیر قرار بگیرند:

```text
offline_packages/paddleocr-models/det
offline_packages/paddleocr-models/rec
offline_packages/paddleocr-models/cls
```

پوشه‌های `det` و `rec` الزامی هستند. پوشه `cls` اختیاری است. برنامه در صورت نبود مدل‌ها تلاش اینترنتی برای دانلود انجام نمی‌دهد و فقط پیام هشدار نمایش می‌دهد.

## Tesseract

اگر از Tesseract هم استفاده شود، باید بسته سیستم‌عاملی Ubuntu به‌صورت آفلاین از مخزن داخلی یا بسته‌های `.deb` نصب شود. فایل‌های زبان فارسی و انگلیسی در این مسیر موجود هستند:

```text
offline_packages/tesseract/tessdata
```

فایل‌های لازم:

```text
fas.traineddata
eng.traineddata
```
