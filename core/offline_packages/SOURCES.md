# منابع بسته آفلاین

فایل‌های این پوشه برای نصب آفلاین از منابع زیر تهیه شده‌اند:

- Python wheels: دانلود شده بر اساس `requirements.txt` از PyPI با دستور `pip download`.
- Tesseract OCR Windows installer:
  `https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe`
- Persian OCR language data:
  `https://github.com/tesseract-ocr/tessdata/raw/main/fas.traineddata`
- English OCR language data:
  `https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata`

نسخه‌ها و checksum فایل‌های دانلود شده را می‌توانید با PowerShell بررسی کنید:

```powershell
Get-FileHash .\offline_packages\python-wheels\*
Get-FileHash .\offline_packages\tesseract\tesseract-ocr-w64-setup-5.5.0.20241111.exe
Get-FileHash .\offline_packages\tesseract\tessdata\*
```
