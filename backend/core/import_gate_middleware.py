from django.http import JsonResponse
from core.import_gate import admit
from internal_api.client import ServiceUnavailable


class ImportGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/imports/"):
            try:
                admit()
            except ServiceUnavailable as exc:
                response = JsonResponse(
                    {"error": {"status": 503, "details": str(exc.detail)}}, status=503
                )
                response["Cache-Control"] = "no-store"
                response["Retry-After"] = "5"
                return response
        return self.get_response(request)
