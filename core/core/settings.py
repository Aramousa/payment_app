import os
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
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'payments.middleware.SingleSessionMiddleware',
    'payments.middleware.EnforceCustomerPasswordChangeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# مدت بی‌فعالیت مجاز قبل از خروج خودکار (ثانیه). پیش‌فرض ۳۰ دقیقه.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv('SESSION_INACTIVITY_TIMEOUT', str(30 * 60)))

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('VISIUNAPP_DB_NAME', 'visiunapp_dev_db'),
        'USER': os.getenv('VISIUNAPP_DB_USER', 'visiunapp_dev_user'),
        'PASSWORD': os.getenv('VISIUNAPP_DB_PASSWORD'),
        'HOST': os.getenv('VISIUNAPP_DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('VISIUNAPP_DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('VISIUNAPP_DB_CONN_MAX_AGE', '60')),
    }
}

if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql' and not DATABASES['default']['PASSWORD']:
    raise ImproperlyConfigured('VISIUNAPP_DB_PASSWORD environment variable is required.')


# Authentication backends
# Custom backend for date-based access control
AUTHENTICATION_BACKENDS = [
    'payments.auth_backend.DateRestrictedBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

X_FRAME_OPTIONS = 'SAMEORIGIN'

EMAIL_BACKEND = os.getenv('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('DJANGO_EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('DJANGO_EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('DJANGO_EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('DJANGO_EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = os.getenv('DJANGO_DEFAULT_FROM_EMAIL', 'noreply@localhost')
