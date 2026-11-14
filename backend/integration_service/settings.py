"""Integration-only deployment. No IAM, sessions, clients or commercial models."""

import os
import re
from django.core.exceptions import ImproperlyConfigured
from config.settings import *  # Shared HTTP/security defaults, not application registration.

INSTALLED_APPS = [
    "rest_framework",
    "integration_service.apps.BoundaryConfig",
    "integration_store",
]
MIDDLEWARE = [
    "core.middleware.GatewayMetadataMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.RequestContextMiddleware",
    "core.import_gate_middleware.ImportGateMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "integration_service.urls"
WSGI_APPLICATION = "integration_service.wsgi.application"
IMPORT_MODEL_APP = "integration_store"
IMPORT_ACCESS = "integration_service.access.RemoteAccess"
CSRF_FAILURE_VIEW = "integration_service.errors.csrf_failure"
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": ["integration_service.access.DelegatedSession"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "integration_service.errors.handler",
}
IAM_URL = os.environ.get("AICED_IAM_URL", "http://127.0.0.1:8001")
INTEGRATION_KEY_ID = os.environ.get("AICED_INTEGRATION_KEY_ID", "integration-v1")
if (
    INTEGRATION_KEY_ID not in AICED_INTERNAL_KEYS
    or AICED_INTERNAL_KEYS[INTEGRATION_KEY_ID]["service"] != "integration"
):
    raise ImproperlyConfigured("Integration requires its own signing key")
for _id, _entry in AICED_INTERNAL_KEYS.items():
    if _id != INTEGRATION_KEY_ID and (
        _entry["service"] != "iam" or _entry["audiences"] != ["integration"]
    ):
        raise ImproperlyConfigured("Only IAM's inbound Integration key is accepted")
INTERNAL_NONCE_MODEL = "integration_store.InternalNonce"
INTEGRATION_SCHEMA = os.environ.get("AICED_INTEGRATION_SCHEMA", "aiced_integration")
if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", INTEGRATION_SCHEMA):
    raise ImproperlyConfigured("Invalid owned schema")
# Explicit role is migrator-only, supplied by the offline deployment command.
_role = os.environ.get("AICED_MIGRATION_ROLE", "")
if _role and not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", _role):
    raise ImproperlyConfigured("Invalid migration role")
DATABASES["default"]["OPTIONS"] = {
    "options": f"-c search_path={INTEGRATION_SCHEMA},pg_catalog -c statement_timeout=15000 "
    "-c idle_in_transaction_session_timeout=15000 -c lock_timeout=5000"
    + (f" -c role={_role}" if _role else "")
}
SPECTACULAR_SETTINGS = {"TITLE": "AICED Data Integration", "VERSION": "1"}
