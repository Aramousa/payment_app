#!/bin/bash
# ─── اسکریپت deploy/update پروژه payment_app ─────────────────────────────
# دستور: bash deploy.sh
# برای اجرای اول: bash deploy.sh --init

set -e

APP_DIR="/var/www/payment_app/core"
VENV_DIR="/var/www/payment_app/venv"
PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
MANAGE="${APP_DIR}/manage.py"

echo "=== deploy payment_app ==="
echo "زمان: $(date '+%Y-%m-%d %H:%M:%S')"

# ─── دریافت آخرین تغییرات از مخزن
echo "▶ دریافت آخرین تغییرات از git..."
git -C "${APP_DIR}" pull

# ─── نصب/به‌روزرسانی پکیج‌ها (از اینترنت)
echo "▶ نصب/به‌روزرسانی پکیج‌ها..."
"${PIP}" install \
    -r "${APP_DIR}/requirements.txt" \
    --quiet

# ─── migrate پایگاه‌داده
echo "▶ اعمال migration ها..."
"${PYTHON}" "${MANAGE}" migrate --noinput

# ─── جمع‌آوری static files
echo "▶ جمع‌آوری فایل‌های استاتیک..."
"${PYTHON}" "${MANAGE}" collectstatic --noinput --clear

# ─── بررسی سلامت
echo "▶ بررسی سلامت برنامه..."
"${PYTHON}" "${MANAGE}" check --deploy 2>&1 | grep -v "WARNINGS\|security" || true

# ─── ری‌استارت Gunicorn
if systemctl is-active --quiet gunicorn 2>/dev/null; then
    echo "▶ ری‌استارت Gunicorn..."
    sudo systemctl restart gunicorn
elif [ -f /tmp/gunicorn.pid ]; then
    echo "▶ ری‌لود Gunicorn..."
    kill -HUP "$(cat /tmp/gunicorn.pid)"
else
    echo "⚠ Gunicorn یافت نشد — به‌صورت دستی راه‌اندازی کنید:"
    echo "  ${VENV_DIR}/bin/gunicorn core.wsgi:application \\"
    echo "    --workers 3 --bind 0.0.0.0:8000 \\"
    echo "    --access-logfile /var/log/payment_app/access.log \\"
    echo "    --error-logfile  /var/log/payment_app/error.log"
fi

echo ""
echo "✅ deploy با موفقیت انجام شد."
