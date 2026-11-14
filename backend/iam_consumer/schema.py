from drf_spectacular.extensions import OpenApiAuthenticationExtension


class DelegatedCookieScheme(OpenApiAuthenticationExtension):
    target_class = "iam_consumer.access.DelegatedSession"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        from django.conf import settings

        return {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}
