import json
import logging
from django.test import SimpleTestCase, RequestFactory
from django.http import JsonResponse
from core.logging import JsonFormatter
from core.middleware import RequestContextMiddleware
from core.request_metrics import request_id


class RequestMetricsTests(SimpleTestCase):
    def test_formatter_never_emits_message_credentials_or_arbitrary_fields(self):
        row=logging.LogRecord('aiced.metrics',logging.INFO,'',0,'SECRET',(),None)
        row.event='request'
        row.metrics={'request_id':'synthetic','seconds':.1,'session_key':'SECRET','sql':'SECRET'}
        result=json.loads(JsonFormatter().format(row))
        self.assertEqual(result['request_id'],'synthetic')
        self.assertEqual(result['seconds'],.1)
        self.assertNotIn('SECRET',json.dumps(result))

    def test_generated_request_id_is_scoped_and_external_id_is_not_trusted(self):
        captured=[]
        def respond(request):
            captured.append(request_id.get())
            return JsonResponse({'ok':True})
        response=RequestContextMiddleware(respond)(RequestFactory().get('/health/',HTTP_X_REQUEST_ID='untrusted'))
        self.assertEqual(response['X-Request-ID'],captured[0])
        self.assertNotEqual(captured[0],'untrusted')
        self.assertIsNone(request_id.get())

    def test_context_is_cleared_on_unhandled_error(self):
        def fail(request):raise RuntimeError('synthetic')
        with self.assertRaises(RuntimeError):
            RequestContextMiddleware(fail)(RequestFactory().get('/health/'))
        self.assertIsNone(request_id.get())
