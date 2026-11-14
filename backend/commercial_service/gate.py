from django.db import connection
from internal_api.client import ServiceUnavailable
from commercial_store.models import RuntimeState

GATE = 591445740000007


def admit():
    if not connection.in_atomic_block:
        raise RuntimeError("Commercial admission requires a transaction")
    with connection.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock_shared(%s)", [GATE])
    if RuntimeState.objects.filter(pk=1, mode="service").exists() is False:
        raise ServiceUnavailable()
