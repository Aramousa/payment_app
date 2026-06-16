import os
from datetime import timedelta
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment files for development.
def _load_local_env_file(path):
    try:
        lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()

        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]

        os.environ.setdefault(key, value)


_load_local_env_file(BASE_DIR / '.env')
_load_local_env_file(BASE_DIR / '.env.postgres.dev')



def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(BASE_DIR / '.env')


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY environment variable is required.')

DEBUG = env_bool('DJANGO_DEBUG', False)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        'DJANGO_ALLOWED_HOSTS',
        'app.rabasa.ir,192.168.1.23,localhost,127.0.0.1',
    ).split(',')
    if host.strip()
]

# Application definition

INSTALLED_APPS = [
    'payments',
    'django_jalali',
    'axes',
    'mfa',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'payments.middleware.SingleSessionMiddleware',
    'payments.middleware.SMSOTPMiddleware',
    'payments.middleware.EnforceCustomerPasswordChangeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# مدت بی‌فعالیت مجاز قبل از خروج خودکار (ثانیه). پیش‌فرض ۱۵ دقیقه.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv('SESSION_INACTIVITY_TIMEOUT', str(15 * 60)))

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'payments' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.csrf',
                'django.contrib.messages.context_processors.messages',
                'payments.context_processors.login_ads',
                'payments.context_processors.unread_notifications',
                'payments.context_processors.app_navigation',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

_db_sslmode = os.getenv('VISIUNAPP_DB_SSLMODE', 'require' if not DEBUG else 'disable')
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('VISIUNAPP_DB_NAME', 'visiunapp_dev_db'),
        'USER': os.getenv('VISIUNAPP_DB_USER', 'visiunapp_dev_user'),
        'PASSWORD': os.getenv('VISIUNAPP_DB_PASSWORD'),
        'HOST': os.getenv('VISIUNAPP_DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('VISIUNAPP_DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('VISIUNAPP_DB_CONN_MAX_AGE', '60')),
        'OPTIONS': {
            'sslmode': _db_sslmode,
        },
    }
}

if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql' and not DATABASES['default']['PASSWORD']:
    raise ImproperlyConfigured('VISIUNAPP_DB_PASSWORD environment variable is required.')


# Authentication backends
# Custom backend for date-based access control
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'payments.auth_backend.DateRestrictedBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

# Argon2 — هش قوی‌تر از PBKDF2 پیش‌فرض Django
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',   # fallback برای رمزهای قدیمی
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# Django با اولین hasher رمز جدید می‌سازد و هنگام login رمزهای قدیمی را upgrade می‌کند.

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'fa'

TIME_ZONE = 'UTC'
APP_DISPLAY_TIME_ZONE = os.getenv('APP_DISPLAY_TIME_ZONE', 'Asia/Tehran')

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# حداکثر حجم فایل در حافظه قبل از نوشتن روی دیسک (2MB)
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

PADDLEOCR_MODEL_DIR = Path(os.getenv('PADDLEOCR_MODEL_DIR', BASE_DIR / 'offline_packages' / 'paddleocr-models'))
PADDLEOCR_DET_MODEL_DIR = Path(os.getenv('PADDLEOCR_DET_MODEL_DIR', PADDLEOCR_MODEL_DIR / 'det'))
PADDLEOCR_REC_MODEL_DIR = Path(os.getenv('PADDLEOCR_REC_MODEL_DIR', PADDLEOCR_MODEL_DIR / 'rec'))
PADDLEOCR_CLS_MODEL_DIR = Path(os.getenv('PADDLEOCR_CLS_MODEL_DIR', PADDLEOCR_MODEL_DIR / 'cls'))

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'DJANGO_CSRF_TRUSTED_ORIGINS',
        'https://app.rabasa.ir,http://192.168.1.23:8080,http://127.0.0.1:8080,http://localhost:8000,http://127.0.0.1:8000',
    ).split(',')
    if origin.strip()
]

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/submit/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = env_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# HSTS — فقط در صورتی که SSL فعال است فعال می‌شود
if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_HSTS_SUBDOMAINS', True)
    SECURE_HSTS_PRELOAD = env_bool('DJANGO_HSTS_PRELOAD', True)

X_FRAME_OPTIONS = 'DENY'

# ─── django-axes: قفل حساب بعد از چند تلاش ناموفق ─────────────────────────
AXES_FAILURE_LIMIT = int(os.getenv('AXES_FAILURE_LIMIT', '5'))
AXES_COOLOFF_TIME = timedelta(minutes=int(os.getenv('AXES_COOLOFF_MINUTES', '15')))
AXES_LOCKOUT_PARAMETERS = ['ip_address', 'username']
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ADMIN = True
AXES_LOCKOUT_TEMPLATE = 'errors/lockout.html'

# ─── django-csp: Content Security Policy ─────────────────────────────────────
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC  = ("'self'", "'unsafe-inline'")
CSP_STYLE_SRC   = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC     = ("'self'", "data:", "blob:")
CSP_FONT_SRC    = ("'self'",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_BASE_URI    = ("'self'",)
CSP_FORM_ACTION = ("'self'",)

# ─── django-mfa2: احراز هویت دو مرحله‌ای ───────────────────────────────────
MFA_UNALLOWED_METHODS = ('U2F',)  # U2F منسوخ شده — FIDO2 جایگزین مدرن آن است
MFA_LOGIN_CALLBACK = 'payments.mfa_hooks.mfa_login_callback'
MFA_RECHECK = True
MFA_RECHECK_MIN = int(os.getenv('MFA_RECHECK_MIN', '10'))
MFA_RECHECK_MAX = int(os.getenv('MFA_RECHECK_MAX', '30'))
MFA_QUICKLOGIN = False
MFA_ALWAYS_GO_TO_LOGIN_PAGE = True
MFA_REDIRECT_AFTER_REGISTRATION = 'mfa_home'
MFA_SUCCESS_REGISTRATION_MSG = 'روش احراز هویت دو مرحله‌ای با موفقیت افزوده شد.'
MFA_HIDE_DISABLE = ()
MFA_EMAIL_FROM = os.getenv('DJANGO_DEFAULT_FROM_EMAIL', 'noreply@localhost')
MFA_RENAME_METHODS = {
    'TOTP':           'اپلیکیشن احراز هویت (TOTP)',
    'Email':          'کد از طریق ایمیل',
    'RECOVERY':       'کد بازیابی',
    'U2F':            'کلید سخت‌افزاری',
    'FIDO2':          'FIDO2',
    'Trusted_Devices': 'دستگاه مورد اعتماد',
}
EMAIL_FROM = 'سامانه ارتباط با مشتری'

# برای TOTP — نام سازمان که در Google Authenticator نمایش داده می‌شود
TOKEN_ISSUER_NAME = os.getenv('MFA_TOKEN_ISSUER', 'سامانه ارتباط با مشتری')

# BASE_URL برای لینک‌های ایمیل در MFA
BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:8000')

# FIDO2 — شناسه سرور باید دقیقاً با domain مرورگر مطابقت داشته باشد
# dev روی 127.0.0.1 → مقدار '127.0.0.1'
# dev روی localhost  → مقدار 'localhost'
# production         → مقدار 'app.rabasa.ir'
FIDO_SERVER_ID   = os.getenv('FIDO_SERVER_ID', 'localhost')
FIDO_SERVER_NAME = os.getenv('FIDO_SERVER_NAME', 'سامانه ارتباط با مشتری')

# U2F — منسوخ شده، فقط برای جلوگیری از crash در صورت وجود داده قدیمی
U2F_APPID = os.getenv('APP_BASE_URL', 'http://localhost:8000')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file_errors': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'errors.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['file_errors'],
            'level': 'ERROR',
            'propagate': False,
        },
        'payments': {
            'handlers': ['file_errors', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ─── ایمیل ────────────────────────────────────────────────────────────────────
# development: ایمیل‌ها در فایل ذخیره می‌شوند (بدون نیاز به SMTP)
# production:  از SMTP واقعی استفاده می‌شود
_default_email_backend = (
    'django.core.mail.backends.filebased.EmailBackend'
    if DEBUG else
    'django.core.mail.backends.smtp.EmailBackend'
)
# ─── Anthropic API — برای OCR هوشمند فیش بانکی ─────────────────────────────
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
# Google Gemini Flash — کاملاً رایگان، بدون کارت اعتباری
# کلید رایگان از: https://aistudio.google.com/app/apikey
GEMINI_API_KEY    = os.getenv('GEMINI_API_KEY', '')
# OCR.space — رایگان تا ۲۵,۰۰۰ درخواست در ماه
# رجیستر رایگان: https://ocr.space/ocrapi/freekey
OCRSPACE_API_KEY  = os.getenv('OCRSPACE_API_KEY', '')

EMAIL_BACKEND = os.getenv('DJANGO_EMAIL_BACKEND', _default_email_backend)
EMAIL_FILE_PATH = BASE_DIR / 'logs' / 'emails'   # محل ذخیره ایمیل‌ها در dev

EMAIL_HOST     = os.getenv('DJANGO_EMAIL_HOST', 'localhost')
EMAIL_PORT     = int(os.getenv('DJANGO_EMAIL_PORT', '25'))
EMAIL_HOST_USER     = os.getenv('DJANGO_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS  = env_bool('DJANGO_EMAIL_USE_TLS', False)
EMAIL_USE_SSL  = env_bool('DJANGO_EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = os.getenv('DJANGO_DEFAULT_FROM_EMAIL', 'noreply@localhost')
