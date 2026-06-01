#!/bin/bash
# ─── نصب آفلاین پکیج‌های پروژه روی سرور لینوکس ───────────────
# پیش‌نیاز: Python 3.13+ و pip نصب شده باشند
# دستور اجرا: bash install.sh [مسیر محیط مجازی]
# مثال:       bash install.sh /home/app/venv

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${1:-/home/app/venv}"
PYTHON="${VENV_PATH}/bin/python"
PIP="${VENV_PATH}/bin/pip"

echo "=== نصب آفلاین پکیج‌های پروژه ==="
echo "محیط مجازی: ${VENV_PATH}"

# ساخت محیط مجازی اگر وجود ندارد
if [ ! -f "${PYTHON}" ]; then
    echo "▶ ساخت محیط مجازی..."
    python3 -m venv "${VENV_PATH}"
fi

echo "▶ نصب پکیج‌ها از پوشه آفلاین..."
"${PIP}" install \
    --no-index \
    --find-links="${SCRIPT_DIR}" \
    asgiref \
    "Django>=6.0" \
    django-jalali \
    et_xmlfile \
    gunicorn \
    jalali_core \
    jdatetime \
    openpyxl \
    packaging \
    pillow \
    pypdf \
    pytesseract \
    sqlparse \
    typing_extensions \
    tzdata \
    user-agents \
    ua-parser \
    ua-parser-builtins

echo ""
echo "✅ نصب با موفقیت انجام شد."
echo ""
echo "⚠  نکته: pytesseract به نرم‌افزار tesseract-ocr نیاز دارد:"
echo "   sudo apt install tesseract-ocr tesseract-ocr-fas"
echo ""
echo "⚠  نکته: psycopg2 (درایور PostgreSQL) در این بسته نیست."
echo "   روی سرور با اینترنت: pip install psycopg2-binary"
echo "   یا با apt: sudo apt install python3-psycopg2"
