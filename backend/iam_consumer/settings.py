"""Compatibility residue: business data remains public; IAM tables denied."""

import os
from config.settings import *

IAM_REMOTE = True
IAM_URL = os.environ.get("AICED_IAM_URL", "http://127.0.0.1:8003")
IAM_CONSUMER_KEY_ID = os.environ.get("AICED_IAM_CONSUMER_KEY_ID", "client-iam-v1")
INSTALLED_APPS = [*INSTALLED_APPS, "iam_consumer"]
MIDDLEWARE = [
    m
    for m in MIDDLEWARE
    if m
    not in [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
    ]
]
MIDDLEWARE.insert(0, "iam_consumer.middleware.RetiredIAMMiddleware")
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": ["iam_consumer.access.DelegatedSession"],
    "UNAUTHENTICATED_USER": None,
}
BUSINESS_ACTOR_MODEL = "iam_consumer.ActorRef"
BUSINESS_ORGANIZATION_MODEL = "iam_consumer.OrganizationRef"
BUSINESS_MEMBERSHIP_MODEL = "iam_consumer.MembershipRef"
INTERNAL_NONCE_MODEL = "iam_consumer.InternalNonce"
# Historical migrations stay in place. Boundary constraints are switched only
# by the guarded offline cutover tool after validating all historical refs.

MIGRATION_MODULES = {
    "clients": "iam_consumer.client_migrations",
    "audit": "iam_consumer.audit_migrations",
}

ROOT_URLCONF = "iam_consumer.urls"

SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_URLCONF": "config.urls",
    "SCHEMA_PATH_PREFIX": "/api",
}

from django.core.exceptions import ImproperlyConfigured

if os.environ.get("AICED_CONSUMER_MIGRATION") != "1":
    from .trust import validate
    validate(AICED_INTERNAL_KEYS, IAM_CONSUMER_KEY_ID)

COMMERCIAL_REMOTE = os.environ.get("AICED_COMMERCIAL_REMOTE") == "1"
COMMERCIAL_AUDIT_URL = os.environ.get("AICED_COMMERCIAL_URL", "")
COMMERCIAL_AUDIT_KEY_ID = os.environ.get("AICED_COMMERCIAL_AUDIT_KEY_ID", "client-commercial-v1")

# Request-scoped connections bound idle sockets in the multi-service HTTP deployment.
DATABASES["default"]["CONN_MAX_AGE"] = 0
