# بسته نصب آفلاین — پروژه payment_app

## محتوا
این پوشه شامل تمام فایل‌های `.whl` لازم برای نصب آفلاین روی سرور Linux با Python 3.13 است.

## پکیج‌های موجود

| پکیج | نسخه | نوع |
|------|------|-----|
| Django | 6.0.2 | Pure Python |
| asgiref | 3.11.1 | Pure Python |
| gunicorn | 23.0.0 | Pure Python |
| django-jalali | 7.4.0 | Pure Python |
| jdatetime | 5.2.0 | Pure Python |
| jalali_core | 1.0.0 | Pure Python |
| openpyxl | 3.1.5 | Pure Python |
| Pillow | 12.1.0 | **Binary — manylinux** |
| pypdf | 6.x | Pure Python |
| pytesseract | 0.3.13 | Pure Python |
| sqlparse | 0.5.5 | Pure Python |
| user-agents | 2.2.0 | Pure Python |
| ua-parser | 1.0.2 | Pure Python |
| tzdata | 2025.3 | Pure Python |

## نصب

```bash
# اجازه اجرا به اسکریپت
chmod +x install.sh

# نصب (مسیر venv اختیاری، پیش‌فرض: /home/app/venv)
bash install.sh /path/to/venv
```

## نیازمندی‌های سیستمی (apt)

```bash
sudo apt update
sudo apt install -y \
    python3.13 python3.13-venv python3.13-dev \
    libpq-dev gcc \
    tesseract-ocr tesseract-ocr-fas \
    postgresql-client
```

## پکیج‌های خارج از این بسته

### psycopg2 (PostgreSQL driver)
چون نیاز به کامپایل دارد، باید روی سرور نصب شود:
```bash
# روش ۱ — با apt
sudo apt install python3-psycopg2

# روش ۲ — با pip (نیاز به اینترنت)
pip install psycopg2-binary
```

### PaddleOCR (اختیاری — OCR پیشرفته)
این پکیج به دلیل حجم بالا در این بسته نیست:
```bash
pip install paddlepaddle paddleocr
```
