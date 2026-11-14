import os
import json
import re
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def positive_int_env(name, default):
    try:
        value = int(os.environ.get(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f'{name} must be a positive integer.') from exc
    if value <= 0:
        raise ImproperlyConfigured(f'{name} must be a positive integer.')
    return value


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must contain at least 32 characters.')
DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
AICED_GATEWAY_KEY = os.environ.get('AICED_GATEWAY_KEY', '')
if AICED_GATEWAY_KEY and (len(AICED_GATEWAY_KEY) < 32 or not all(
        c.isascii() and (c.isalnum() or c in '_-') for c in AICED_GATEWAY_KEY)):
    raise ImproperlyConfigured('AICED_GATEWAY_KEY requires at least 32 URL-safe characters.')
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'rest_framework', 'drf_spectacular', 'identity', 'core', 'clients', 'audit', 'ingestion',
]
MIDDLEWARE = [
    'core.middleware.GatewayMetadataMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.RequestContextMiddleware',
    'core.import_gate_middleware.ImportGateMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': os.environ.get('POSTGRES_DB', 'aiced'),
    'USER': os.environ.get('POSTGRES_USER', 'aiced'),
    'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
    'HOST': os.environ.get('POSTGRES_HOST', 'db'),
    'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    'CONN_MAX_AGE': 60,
}}
AUTH_USER_MODEL = 'identity.User'
AICED_INTERNAL_KEYS = json.loads(os.environ.get('AICED_INTERNAL_KEYS', '{}'))
if not isinstance(AICED_INTERNAL_KEYS,dict):
    raise ImproperlyConfigured('AICED_INTERNAL_KEYS must be an object.')
_internal_secrets = set()
for _key_id, _key in AICED_INTERNAL_KEYS.items():
    if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',_key_id)
            or not isinstance(_key, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{32,128}',_key.get('secret',''))
            or _key.get('secret') in (SECRET_KEY, AICED_GATEWAY_KEY)
            or _key.get('secret') in _internal_secrets
            or _key.get('service') not in ('iam','client_crm','commercial','integration')
            or not isinstance(_key.get('audiences'), list)
            or not set(_key['audiences']) <= {'iam','client','audit','integration'}):
        raise ImproperlyConfigured('Invalid AICED_INTERNAL_KEYS configuration.')
    _internal_secrets.add(_key['secret'])
INTEGRATION_AUDIT_URL = os.environ.get('AICED_INTEGRATION_AUDIT_URL', '')
INTEGRATION_AUDIT_KEY_ID = os.environ.get('AICED_INTEGRATION_AUDIT_KEY_ID', 'iam-integration-v1')
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Tunis'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 1800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
API_MAX_JSON_BYTES = positive_int_env('API_MAX_JSON_BYTES', str(64 * 1024))
DATA_UPLOAD_MAX_MEMORY_SIZE = API_MAX_JSON_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['core.permissions.DenyAll'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['core.parsers.BoundedJSONParser'],
    'EXCEPTION_HANDLER': 'core.errors.api_exception_handler',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}
CSRF_FAILURE_VIEW = 'core.errors.csrf_failure'
LOGIN_WINDOW_SECONDS = positive_int_env('LOGIN_WINDOW_SECONDS', '900')
AUTH_LOCK_TIMEOUT_MS = positive_int_env('AUTH_LOCK_TIMEOUT_MS', '5000')
LOGIN_ACCOUNT_LIMIT = positive_int_env('LOGIN_ACCOUNT_LIMIT', '10')
LOGIN_IP_LIMIT = positive_int_env('LOGIN_IP_LIMIT', '30')
IMPORT_MAX_DAILY_BATCHES = positive_int_env('IMPORT_MAX_DAILY_BATCHES', '50')
IMPORT_MAX_STAGED_BATCHES = positive_int_env('IMPORT_MAX_STAGED_BATCHES', '20')
SPECTACULAR_SETTINGS = {
    'TITLE': 'AICED API', 'VERSION': '0.1.0', 'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {'ProspectStatusEnum':'clients.models.Prospect.Status', 'OpportunityStatusEnum':['open','won','lost'], 'AccessScopeEnum': 'identity.models.RoleAssignment.Scope', 'PartyKindEnum':'clients.models.Party.Kind', 'InteractionKindEnum':['call','email','meeting','visit'], 'ImportDateFormatEnum':'ingestion.models.DATE_FORMAT_CHOICES'},
}
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'formatters': {'json': {'()': 'core.logging.JsonFormatter'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'json'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
