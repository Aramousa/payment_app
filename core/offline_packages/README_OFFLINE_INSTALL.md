# نصب آفلاین وابستگی‌ها

این پوشه برای نصب آفلاین امکانات برنامه آماده شده است.

## نصب پکیج‌های Python

از ریشه پروژه اجرا کنید:

```powershell
.\offline_packages\install_offline.ps1
```

یا به‌صورت دستی:

```powershell
.\venv\Scripts\python.exe -m pip install --no-index --find-links .\offline_packages\python-wheels -r .\requirements.txt
```

## فعال‌سازی OCR عکس فاکتور

برای خواندن متن از عکس، فقط `pytesseract` کافی نیست و خود Tesseract OCR هم باید روی ویندوز نصب باشد.

فایل نصب داخل این مسیر قرار دارد:

```text
offline_packages\tesseract\tesseract-ocr-w64-setup-5.5.0.20241111.exe
```

بعد از نصب Tesseract، فایل‌های زبان را از این مسیر:

```text
offline_packages\tesseract\tessdata
```

به مسیر `tessdata` نصب Tesseract کپی کنید. مسیر معمول ویندوز:

```text
C:\Program Files\Tesseract-OCR\tessdata
```

حداقل این دو فایل لازم است:

```text
fas.traineddata
eng.traineddata
```

بعد از نصب، اگر `tesseract.exe` در PATH نبود، مسیر زیر را به PATH ویندوز اضافه کنید:

```text
C:\Program Files\Tesseract-OCR
```

## تست نصب OCR

```powershell
tesseract --list-langs
```

باید `fas` و `eng` در خروجی دیده شوند.
