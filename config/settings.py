"""PostgreSQL obligatorio. HTTP solo para el entorno local explícito."""
import os
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL = os.environ.get('DJANGO_LOCAL') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured('Configure DJANGO_SECRET_KEY con al menos 32 caracteres.')
DEBUG = False
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1' if LOCAL else '').split(',')
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get('DJANGO_CSRF_ORIGINS', '').split(',')))
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
                  'django.contrib.messages', 'django.contrib.staticfiles', 'gestion']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
              'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
              'django.contrib.auth.middleware.AuthenticationMiddleware', 'gestion.middleware.SessionPolicyMiddleware',
              'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR/'templates'],
              'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request',
              'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages', 'gestion.middleware.identity_context']}}]
WSGI_APPLICATION = 'config.wsgi.application'
uri = urlparse(os.environ.get('DATABASE_URL', ''))
if uri.scheme not in ('postgres', 'postgresql') or not uri.hostname:
    raise ImproperlyConfigured('DATABASE_URL debe señalar PostgreSQL.')
sslmode = parse_qs(uri.query).get('sslmode', ['disable' if LOCAL else 'verify-full'])[0]
if not LOCAL and sslmode != 'verify-full':
    raise ImproperlyConfigured('Producción exige sslmode=verify-full.')
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': unquote(uri.path.lstrip('/')),
    'USER': unquote(uri.username or ''), 'PASSWORD': unquote(uri.password or ''),
    'HOST': uri.hostname, 'PORT': uri.port or 5432, 'CONN_MAX_AGE': 0,
    'OPTIONS': {'sslmode': sslmode, 'connect_timeout': 10}, 'ATOMIC_REQUESTS': False}}
AUTH_USER_MODEL = 'gestion.Account'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher']
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
                             'OPTIONS': {'min_length': 15}},
 {'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},
 {'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}]
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Costa_Rica'
USE_TZ = True
STATIC_URL = '/static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not LOCAL
CSRF_COOKIE_SECURE = not LOCAL
SESSION_COOKIE_AGE = 8*60*60
SECURE_SSL_REDIRECT = not LOCAL
SECURE_HSTS_SECONDS = 0 if LOCAL else 31536000
# Cloud Run elimina/informa estas cabeceras en su frontera; no exponer Gunicorn directo en producción.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if not LOCAL else None
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 2*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024*1024
TRUSTED_PUBLIC_KEY_FILES = list(filter(None, os.environ.get('VERDEAZUL_TRUSTED_PUBLIC_KEYS', '').split(os.pathsep)))

IDENTITY_KEY_FILE = os.environ.get("VERDEAZUL_IDENTITY_KEY_FILE", "")
