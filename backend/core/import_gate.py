"""Local database admission gates for deployment freeze and single-writer cutover.

The advisory lock is held until the business transaction commits. Deployment
administration takes the exclusive counterpart before changing the mode. Each
runtime reads only its own control table; no cross-service SQL is performed.
"""

from django.apps import apps
from django.conf import settings
from django.db import connection
from internal_api.client import ServiceUnavailable

LEGACY_GATE = 591445740000001
SERVICE_GATE = 591445740000002


def spec():
    owned = getattr(settings, "IMPORT_MODEL_APP", "ingestion") == "integration_store"
    return (
        "integration_store" if owned else "ingestion",
        "service" if owned else "legacy",
        SERVICE_GATE if owned else LEGACY_GATE,
    )


def mode():
    app, default, _ = spec()
    row = (
        apps.get_model(app, "RuntimeState")
        .objects.filter(pk=1)
        .values_list("mode", flat=True)
        .first()
    )
    return row or default


def admit(lock=False):
    _, expected, key = spec()
    if lock:
        if not connection.in_atomic_block:
            raise RuntimeError("Import admission needs a local transaction")
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('lock_timeout','5000ms',true)")
            cursor.execute("SELECT pg_advisory_xact_lock_shared(%s)", [key])
    if mode() != expected:
        raise ServiceUnavailable(
            "Imports suspendus pour bascule contrôlée. Réessayez après la maintenance."
        )
