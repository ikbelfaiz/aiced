"""Commercial-owned runtime. No Client, IAM, sessions or import ORM models."""

import os, re
from django.core.exceptions import ImproperlyConfigured
from config.settings import *

INSTALLED_APPS = [
    "rest_framework",
    "commercial_service.apps.BoundaryConfig",
    "commercial_store",
]
MIDDLEWARE = [
    "core.middleware.GatewayMetadataMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.RequestContextMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
CSRF_FAILURE_VIEW = "commercial_service.errors.csrf_failure"
ROOT_URLCONF = "commercial_service.urls"
WSGI_APPLICATION = "commercial_service.wsgi.application"
INTERNAL_NONCE_MODEL = "commercial_store.InternalNonce"
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": ["commercial_service.access.DelegatedSession"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "commercial_service.errors.handler",
}
IAM_URL = os.environ.get("AICED_IAM_URL", "http://127.0.0.1:8001")
CLIENT_URL = os.environ.get("AICED_CLIENT_URL", "http://127.0.0.1:8000")
COMMERCIAL_IAM_KEY_ID = os.environ.get(
    "AICED_COMMERCIAL_IAM_KEY_ID", "commercial-iam-v1"
)
COMMERCIAL_CLIENT_KEY_ID = os.environ.get(
    "AICED_COMMERCIAL_CLIENT_KEY_ID", "commercial-client-v1"
)
if COMMERCIAL_IAM_KEY_ID == COMMERCIAL_CLIENT_KEY_ID:
    raise ImproperlyConfigured("Commercial requires distinct pairwise identities")
for ident, audiences in [
    (COMMERCIAL_IAM_KEY_ID, {"iam", "audit"}),
    (COMMERCIAL_CLIENT_KEY_ID, {"client"}),
]:
    key = AICED_INTERNAL_KEYS.get(ident, {})
    if (
        key.get("service") != "commercial"
        or not key.get("audiences")
        or set(key["audiences"]) != audiences
    ):
        raise ImproperlyConfigured("Invalid Commercial signing identity")
for ident, key in AICED_INTERNAL_KEYS.items():
    if ident not in (COMMERCIAL_IAM_KEY_ID, COMMERCIAL_CLIENT_KEY_ID) and not (
        key["service"] == "client_crm" and key["audiences"] == ["commercial"]
    ):
        raise ImproperlyConfigured(
            "Commercial accepts only scoped Client audit ingress"
        )
COMMERCIAL_SCHEMA = os.environ.get("AICED_COMMERCIAL_SCHEMA", "aiced_commercial")
role = os.environ.get("AICED_MIGRATION_ROLE", "")
if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", COMMERCIAL_SCHEMA) or (
    role and not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", role)
):
    raise ImproperlyConfigured("Invalid Commercial schema or migrator")
DATABASES["default"]["OPTIONS"] = {
    "options": f"-c search_path={COMMERCIAL_SCHEMA},pg_catalog -c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000"
    + (f" -c role={role}" if role else "")
}

# Request-scoped connections bound idle sockets in the multi-service HTTP deployment.
DATABASES["default"]["CONN_MAX_AGE"] = 0
