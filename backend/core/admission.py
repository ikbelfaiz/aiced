"""Database-scoped revocation coordination, with no IAM ORM dependency."""

from django.conf import settings
from django.db import connection

AUTH_BARRIER = 4711239301896721


def barrier(exclusive=False):
    if not connection.in_atomic_block:
        raise RuntimeError("Authorization admission requires a local transaction")
    function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('lock_timeout', %s, true)",
            [f"{settings.AUTH_LOCK_TIMEOUT_MS}ms"],
        )
        cursor.execute(f"SELECT {function}(%s)", [AUTH_BARRIER])


def remote_write(authorize, change, audit):
    from django.db import transaction
    from rest_framework.exceptions import PermissionDenied

    with transaction.atomic():
        barrier()
        decision = authorize()
        if not isinstance(decision, dict) or decision.get("authorized") is not True:
            raise PermissionDenied("Décision d’autorisation invalide.")
        result = change(decision)
        if audit(decision, result) is None:
            raise RuntimeError("Required local audit did not return an event")
        return result
