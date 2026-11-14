from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from core.middleware import GatewayMetadataMiddleware


@override_settings(AICED_GATEWAY_KEY="synthetic-edge-" + "x" * 40)
class GatewayMetadataTests(SimpleTestCase):
    def call(self, **headers):
        request = RequestFactory().get("/api/health/", **headers)
        middleware = GatewayMetadataMiddleware(
            lambda req: JsonResponse(
                {
                    "secure": req.is_secure(),
                    "ip": req.META["REMOTE_ADDR"],
                    "key_visible": "HTTP_X_AICED_GATEWAY_KEY" in req.META,
                }
            )
        )
        return middleware(request)

    def test_signed_edge_metadata_and_tls_are_applied_before_security(self):
        response = self.call(
            HTTP_X_AICED_GATEWAY_KEY="synthetic-edge-" + "x" * 40,
            HTTP_X_AICED_CLIENT_IP="2001:db8::1",
            HTTP_X_AICED_PROTO="https",
        )
        self.assertJSONEqual(
            response.content,
            {"secure": True, "ip": "2001:db8::1", "key_visible": False},
        )

    def test_untrusted_headers_cannot_forge_ip_or_tls(self):
        for key in ["", "forged", "clé-invalide"]:
            response = self.call(
                HTTP_X_AICED_GATEWAY_KEY=key,
                HTTP_X_AICED_CLIENT_IP="192.0.2.1",
                HTTP_X_AICED_PROTO="https",
                HTTP_X_FORWARDED_PROTO="https",
                HTTP_X_FORWARDED_FOR="192.0.2.1",
            )
            self.assertJSONEqual(
                response.content,
                {"secure": False, "ip": "127.0.0.1", "key_visible": False},
            )

    def test_invalid_authenticated_metadata_fails_closed(self):
        for ip, scheme in [("forged", "https"), ("127.0.0.1", "https,http")]:
            response = self.call(
                HTTP_X_AICED_GATEWAY_KEY="synthetic-edge-" + "x" * 40,
                HTTP_X_AICED_CLIENT_IP=ip,
                HTTP_X_AICED_PROTO=scheme,
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(AICED_GATEWAY_KEY="")
    def test_direct_mode_disables_all_edge_metadata_trust(self):
        response = self.call(
            HTTP_X_AICED_GATEWAY_KEY="synthetic-edge-" + "x" * 40,
            HTTP_X_AICED_CLIENT_IP="192.0.2.1",
            HTTP_X_AICED_PROTO="https",
        )
        self.assertJSONEqual(
            response.content, {"secure": False, "ip": "127.0.0.1", "key_visible": False}
        )
