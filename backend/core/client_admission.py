"""One-database Client scope fence. Readers over HTTP must be stateless.

Order: local org serialization, IAM barrier, Client scope fence, fresh remote
checks, local mutation/audit, commit. Conservative global fence, no RPC locks.
"""

from django.conf import settings
from django.db import connection
from .admission import barrier

CLIENT_SCOPE_BARRIER = 591445740000006


def scope_fence(exclusive=False):
    if not connection.in_atomic_block:
        raise RuntimeError("Client scope admission requires a local transaction")
    barrier()
    function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('lock_timeout', %s, true)",
            [f"{settings.AUTH_LOCK_TIMEOUT_MS}ms"],
        )
        cursor.execute(f"SELECT {function}(%s)", [CLIENT_SCOPE_BARRIER])
