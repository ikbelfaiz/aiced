from django.http import JsonResponse
from django.core.exceptions import RequestDataTooBig
from rest_framework.views import exception_handler
from audit.services import record
from .parsers import PayloadTooLarge


def api_exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        exc = PayloadTooLarge()
    response = exception_handler(exc, context)
    if response is not None:
        request = context['request']
        if response.status_code in (401, 403, 404):
            record('access.denied', actor=request.user, result='denied', request=request)
        response.data = {'error': {'status': response.status_code, 'details': response.data}}
    return response


def csrf_failure(request, reason=''):
    record('csrf.denied', actor=getattr(request, 'user', None), result='denied', request=request)
    return JsonResponse({'error': {'status': 403, 'details': 'Vérification CSRF échouée.'}}, status=403)
