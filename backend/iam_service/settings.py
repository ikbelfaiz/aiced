"""IAM-owned deployment; no Client/Commercial/Integration ORM registration."""

import os
from django.core.exceptions import ImproperlyConfigured
from config.settings import *

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
    "identity",
    "audit",
    "core",
    "iam_control",
    "iam_service.apps.IAMConfig",
]
MIDDLEWARE = [
    m for m in MIDDLEWARE if m != "core.import_gate_middleware.ImportGateMiddleware"
]
MIDDLEWARE.insert(0, "iam_control.middleware.AdmissionMiddleware")
ROOT_URLCONF = "iam_service.urls"
WSGI_APPLICATION = "iam_service.wsgi.application"
MIGRATION_MODULES = {
    "identity": "iam_service.migrations.identity",
    "audit": "iam_service.migrations.audit",
}
DATABASES["default"]["OPTIONS"] = {
    "options": "-c search_path=aiced_iam,pg_catalog -c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000"
}
_role = os.environ.get("AICED_MIGRATION_ROLE", "")
if _role:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", _role):
        raise ImproperlyConfigured("Invalid migration role")
    DATABASES["default"]["OPTIONS"]["options"] += f" -c role={_role}"
IAM_OWNED = True
INTEGRATION_AUDIT_URL = ""
