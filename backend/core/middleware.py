import uuid
import hmac
import ipaddress
from django.conf import settings
from django.http import JsonResponse


class GatewayMetadataMiddleware:
    """Trust connection metadata only from our authenticated edge, never XFF.

    This key authenticates infrastructure, not users. Session/CSRF and every
    business permission remain mandatory. Empty configuration is direct mode.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.META.pop('HTTP_X_AICED_GATEWAY_KEY', '')
        address = request.META.pop('HTTP_X_AICED_CLIENT_IP', '')
        scheme = request.META.pop('HTTP_X_AICED_PROTO', '')
        key = settings.AICED_GATEWAY_KEY
        if key and hmac.compare_digest(supplied.encode(), key.encode()):
            try:
                address = str(ipaddress.ip_address(address))
                if scheme not in ('http', 'https'):
                    raise ValueError('Invalid scheme')
            except ValueError:
                response = JsonResponse({'error': {'status': 400, 'details': 'Métadonnées Gateway invalides.'}}, status=400)
                response['Cache-Control'] = 'no-store'
                return response
            request.META['REMOTE_ADDR'] = address
            request.META['wsgi.url_scheme'] = scheme
        return self.get_response(request)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4()
        response = self.get_response(request)
        response['X-Request-ID'] = str(request.request_id)
        if request.path.startswith(('/api/', '/internal/')):
            response['Cache-Control'] = 'no-store'
        return response
