from django.http import JsonResponse


class RetiredIAMMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        import re
        if getattr(settings, "COMMERCIAL_REMOTE", False) and re.fullmatch(r"/api/clients/[^/]+/opportunities/(?:[^/]+/)?", request.path):
            return JsonResponse({"error":{"status":503,"details":"Utiliser le service Commercial via le Gateway."}},status=503)

        if (
            request.path.startswith(("/api/auth/", "/api/organizations/"))
            or request.path == "/api/session/"
        ):
            return JsonResponse(
                {
                    "error": {
                        "status": 503,
                        "details": "Utiliser le service IAM via le Gateway.",
                    }
                },
                status=503,
            )
        return self.get_response(request)
