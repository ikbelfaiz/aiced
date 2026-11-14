from django.http import JsonResponse
from django.db import connection, transaction

GATE = 591445740000003


def admit(lock=False):
    from iam_control.models import RuntimeState
    from internal_api.client import ServiceUnavailable

    if lock:
        if not connection.in_atomic_block:
            raise RuntimeError("IAM admission needs transaction")
        with connection.cursor() as c:
            c.execute("SELECT pg_advisory_xact_lock_shared(%s)", [GATE])
    if RuntimeState.objects.filter(pk=1, mode="service").exists() is False:
        raise ServiceUnavailable("IAM suspendu pendant le transfert.")


class AdmissionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/health/"):
            # Hold admission through the entire HTTP request including session saves.
            with transaction.atomic():
                try:
                    admit(lock=True)
                except Exception:
                    return JsonResponse(
                        {
                            "error": {
                                "status": 503,
                                "details": "IAM temporairement indisponible.",
                            }
                        },
                        status=503,
                        headers={"Cache-Control": "no-store"},
                    )
                response = self.get_response(request)
                # Django converts exceptions to responses inside middleware: explicitly
                # rollback error responses so failed audit/session changes cannot commit.
                if response.status_code >= 500:
                    transaction.set_rollback(True)
                return response
        return self.get_response(request)
