from io import BytesIO
from django.conf import settings
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser


class PayloadTooLarge(APIException):
    status_code = 413
    default_detail = 'Le corps JSON dépasse la taille autorisée.'
    default_code = 'payload_too_large'


class BoundedJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        # Bound actual parser bytes as defense in depth for custom streams and
        # framework changes; do not rely only on a Content-Length declaration.
        body = bytearray()
        while len(body) <= settings.API_MAX_JSON_BYTES:
            chunk = stream.read(settings.API_MAX_JSON_BYTES + 1 - len(body))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) > settings.API_MAX_JSON_BYTES:
            raise PayloadTooLarge()
        try:
            return super().parse(BytesIO(body), media_type, parser_context)
        except RecursionError as exc:
            raise ParseError('La structure JSON est trop imbriquée.') from exc
