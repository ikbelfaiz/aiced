from django.core.exceptions import RequestDataTooBig
from rest_framework.views import exception_handler
from core.parsers import PayloadTooLarge
from .journal import record


def csrf_failure(request, reason=""):
    from django.http import JsonResponse

    return JsonResponse(
        {"error": {"status": 403, "details": "Vérification CSRF échouée."}}, status=403
    )


def handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        exc = PayloadTooLarge()
    response = exception_handler(exc, context)
    if response is not None:
        request = context["request"]
        if response.status_code in (401, 403, 404):
            record(
                "access.denied", actor=request.user, result="denied", request=request
            )
        response.data = {
            "error": {"status": response.status_code, "details": response.data}
        }
    return response
