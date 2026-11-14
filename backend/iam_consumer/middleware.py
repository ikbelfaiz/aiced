from django.http import JsonResponse


class RetiredIAMMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
