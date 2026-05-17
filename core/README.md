# Payment App

این پروژه یک سامانه ثبت و بررسی فیش‌های واریزی با استفاده از جنگو است. برنامه برای اجرا در محیط آفلاین و بدون دسترسی به اینترنت طراحی شده است و تمامی وابستگی‌های لازم در خود پروژه قرار دارند.

## ساختار کلی

- `core/` : تنظیمات و ماژول اصلی Django
- `payments/` : اپلیکیشن اصلی با مدل‌ها، فرم‌ها، ویوها و قالب‌ها
- `static/` : منابع استاتیک محلی شامل CSS، JS و فونت
- `media/` : محل ذخیره اسناد و فایل‌های بارگذاری شده (دینامیک)
- `staticfiles/` : محل کلاسیک‌شده‌ی منابع استاتیک پس از `collectstatic`
- `vendor/` : بسته‌های آفلاین Python برای نصب بدون اینترنت
- `db.sqlite3` : دیتابیس محلی نمونه (در صورت نیاز قابل استفاده)

## وابستگی‌های Python

فایل وابستگی:
- `requirements.txt` : فایل واحد نصب آفلاین. این فایل با شرط نسخه پایتون، روی Python 3.10/3.11 از Django 5.2.12 و روی Python 3.12+ از Django 6.0.2 استفاده می‌کند.

## بسته‌های آفلاین

پوشه‌های `vendor/` شامل wheelهای آماده نصب هستند:
- `vendor/wheels/` : بسته‌های ویندوز برای `requirements.txt`
- `vendor/wheels-linux/` : بسته‌های لینوکس برای Python 3.13+ و `requirements.txt`
- `vendor/wheels-linux-py310-django52/` : بسته‌های لینوکس برای Python 3.10 و همان `requirements.txt`

> اگر از سرور آفلاین استفاده می‌کنید، حتما باید از گزینه `--no-index --find-links=...` استفاده کنید و به اینترنت متصل نباشید.
> در بسته انتشار عملیاتی باید کل پوشه `vendor/` همراه پروژه کپی شود. اگر این پوشه روی سرور وجود نداشته باشد، نصب آفلاین با خطای پیدا نشدن بسته‌هایی مثل `asgiref`، `Django` یا `gunicorn` متوقف می‌شود.

## نصب آفلاین

### ویندوز

```powershell
python -m pip install --no-index --find-links=vendor/wheels -r requirements.txt
```

### لینوکس با Python 3.13+

```bash
python3.13 -m pip install --no-index --find-links=vendor/wheels-linux -r requirements.txt
```

### لینوکس با Python 3.10

```bash
python3.10 -m pip install --no-index --find-links=vendor/wheels-linux-py310-django52 -r requirements.txt
```

## تنظیم محیط

در ریشه پروژه یک فایل `.env` می‌تواند شامل مقادیر زیر باشد:

```ini
DJANGO_SECRET_KEY=your_secret_key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_SESSION_COOKIE_SECURE=False
DJANGO_CSRF_COOKIE_SECURE=False
```

> حتما `DJANGO_SECRET_KEY` را برای محیط تولید مقداردهی امن کنید.

## مراحل راه‌اندازی

1. نصب وابستگی‌ها با بسته‌های آفلاین
2. اجرای مهاجرت‌ها:

```bash
python manage.py migrate
```

3. کنترل دسترسی نوشتن دیتابیس و فایل‌های runtime:

```bash
python manage.py check_runtime_storage
```

اگر این دستور خطا داد، مالکیت یا سطح دسترسی فایل `db.sqlite3`، پوشه پروژه، و پوشه `media/` برای کاربر سرویس‌دهنده وب درست نیست. در این حالت ورود و خروج کاربران ممکن است با خطای 500 روبه‌رو شود، چون Django باید نشست کاربر را در جدول session ذخیره یا حذف کند.

4. ساخت فایل‌های استاتیک:

```bash
python manage.py collectstatic --noinput
```

5. اجرای سرور توسعه:

```bash
python manage.py runserver
```

## اجرای پروژه

پس از نصب و راه‌اندازی، آدرس پیش‌فرض:

- `http://127.0.0.1:8000/`

مسیر اصلی فرم ثبت فیش:

- `/submit/`

## منابع استاتیک

این پروژه از منابع محلی استفاده می‌کند و هیچ CDN اینترنتی در قالب‌ها ندارد. فایل‌های مهم:

- `static/js/jquery.min.js`
- `static/js/persian-datepicker.min.js`
- `static/js/cleave.min.js`
- `static/js/bank-autocomplete.js`
- `static/css/app-ui.css`
- `static/css/font-face.css`
- `static/fonts/`

## نکات مهم

- `db.sqlite3` و `media/` و `staticfiles/` فایل‌های runtime هستند و نباید به عنوان وابستگی نصب در بسته آفلاین اضافه شوند.
- اگر بخواهید وابستگی جدیدی اضافه کنید، پس از بروزرسانی `requirements.txt` باید wheel جدید را هم به `vendor/` اضافه کنید.
- برای اجرا روی سرور بدون اینترنت، مطمئن شوید Python و pip روی سرور نصب شده و wheelهای `vendor/` به آن منتقل شده‌اند.

## نحوه به‌روزرسانی

1. **به‌روزرسانی وابستگی‌ها**
   - اگر بسته‌ای جدید اضافه کردید یا نسخه‌ای را تغییر دادید، ابتدا `requirements.txt` را اصلاح کنید.
   - اگر فقط نیازمندید در محیط آفلاین همان مجموعه فعلی را نصب کنید، همین فایل‌ها کافی هستند.

2. **به‌روزرسانی wheelهای آفلاین**
   - در یک ماشین توسعه با اینترنت، wheelهای مورد نیاز را از PyPI دانلود کنید.
   - برای Windows را در `vendor/wheels/` قرار دهید.
   - برای لینوکس Python 3.13+ را در `vendor/wheels-linux/` قرار دهید.
   - برای لینوکس Python 3.10 را در `vendor/wheels-linux-py310-django52/` قرار دهید.

3. **اطمینان از تطابق نسخه‌ها**
   - نسخه‌های داخل `vendor/` باید با فایل requirements مطابقت داشته باشند.
   - اگر نسخه‌ی Django یا هر بسته‌ی دیگری را تغییر دادید، پوشه‌ی wheel مربوطه را نیز به‌روزرسانی کنید.

4. **اضافه کردن منابع فرانت‌اند جدید**
   - هر فایل JS/CSS/فونت جدید باید داخل `static/` اضافه شود.
   - قالب‌ها نباید به CDN یا لینک اینترنتی ارجاع دهند.

5. **تست قبل از انتشار**
   - پس از تغییر dependency یا asset، در محیط توسعه اجرا کنید:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

6. **انتشار روی سرور آفلاین**
   - کد و `vendor/` را به سرور منتقل کنید.
   - در سرور آفلاین، نصب را با دستور `pip install --no-index --find-links=...` انجام دهید.
   - سپس مهاجرت و collectstatic را اجرا کنید.

7. **اگر Python یا معماری سرور تغییر کند**
   - برای سرور آفلاین با معماری یا نسخه‌ی Python متفاوت، باید wheelهای مناسب آن محیط تولید یا دانلود شوند.

## فارسی‌سازی و تاریخ شمسی

این پروژه از `django-jalali` برای پشتیبانی تاریخ شمسی استفاده می‌کند و همه تاریخ‌ها در فرم ثبت فیش با تقویم جعلی نمایش داده می‌شوند.

## اطلاعات بیشتر

اگر نیاز دارید مستندات نصب آفلاین یا راهنمای تغییر نسخه‌ها را تکمیل کنم، آماده هستم کمک کنم.
