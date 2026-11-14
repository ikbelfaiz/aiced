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

if os.environ.get("AICED_CONSUMER_MIGRATION") != "1" and (
    IAM_CONSUMER_KEY_ID not in AICED_INTERNAL_KEYS
    or any(
        key["service"] != "client_crm"
        or not set(key["audiences"]) <= {"iam", "audit", "integration"}
        for key in AICED_INTERNAL_KEYS.values()
    )
):
    raise ImproperlyConfigured("Consumer requires only its own signing identities")
