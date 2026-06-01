#!/bin/bash
# ─── نصب آفلاین پکیج‌های پروژه روی سرور لینوکس ───────────────────────────
# پیش‌نیاز: Python 3.13+ و pip نصب شده باشند
# دستور اجرا: bash install.sh [مسیر venv اختیاری]
# مثال:       bash install.sh /var/www/payment_app/venv

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${1:-/var/www/payment_app/venv}"
PIP="${VENV}/bin/pip"
PYTHON="${VENV}/bin/python"

echo "=== نصب آفلاین پروژه payment_app ==="
echo "محیط مجازی: ${VENV}"
echo ""

# ساخت venv اگر وجود ندارد
if [ ! -f "${PYTHON}" ]; then
    echo "▶ ساخت محیط مجازی Python..."
    python3 -m venv "${VENV}"
fi

# ارتقای pip
"${PIP}" install --no-index --find-links="${SCRIPT_DIR}" pip --upgrade 2>/dev/null || true

echo "▶ نصب پکیج‌ها از پوشه آفلاین..."
"${PIP}" install \
    --no-index \
    --find-links="${SCRIPT_DIR}" \
    asgiref \
    Django \
    django-jalali \
    et_xmlfile \
    gunicorn \
    jalali_core \
    jdatetime \
    openpyxl \
    packaging \
    pillow \
    psycopg2-binary \
    PyMuPDF \
    pypdf \
    pytesseract \
    sqlparse \
    typing_extensions \
    tzdata \
    ua-parser \
    ua-parser-builtins \
    user-agents

echo ""
echo "✅ پکیج‌ها با موفقیت نصب شدند."
echo ""
echo "─── گام‌های بعدی: ───────────────────────────────────────────"
echo " ۱. فایل .env را در مسیر پروژه بسازید (نمونه: .env.example)"
echo " ۲. دستور migrate را اجرا کنید:"
echo "    \${VENV}/bin/python manage.py migrate"
echo " ۳. static files را جمع‌آوری کنید:"
echo "    \${VENV}/bin/python manage.py collectstatic --noinput"
echo " ۴. سرور Gunicorn را راه‌اندازی کنید"
echo ""
echo "⚠  اگر tesseract-ocr برای OCR نیاز است:"
echo "   sudo apt install tesseract-ocr tesseract-ocr-fas"
