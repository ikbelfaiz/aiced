from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework.response import Response
from ingestion.sources import CarthagoReadOnlySource, ManualExcelSource, SyntheticReadOnlySource


class SkeletonTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_liveness_is_public_and_minimal(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_anonymous_session_and_schema_are_denied(self):
        for url in ['/api/session/', '/api/schema/']:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_session_exposes_only_current_user(self):
        user = get_user_model().objects.create_user(username='synthetic-user', password='synthetic-test-password')
        self.client.force_login(user)
        response = self.client.get('/api/session/')
        self.assertEqual(response.json(), {'id': str(user.pk), 'username': user.username})
        self.assertEqual(self.client.post('/api/session/', {}).status_code, 403)

    def test_default_policy_denies_even_authenticated_superuser(self):
        class FutureView(APIView):
            def get(self, request):
                return Response({'secret': True})
        user = get_user_model().objects.create_superuser(username='synthetic-admin', password='synthetic-test-password')
        request = APIRequestFactory().get('/')
        from rest_framework.test import force_authenticate
        force_authenticate(request, user=user)
        self.assertEqual(FutureView.as_view()(request).status_code, 403)

    def test_unapproved_ingestion_fails_explicitly(self):
        for source in [CarthagoReadOnlySource(), ManualExcelSource()]:
            with self.assertRaises(NotImplementedError):
                source.read()

    def test_synthetic_adapter_is_read_only_and_explicit(self):
        adapter = SyntheticReadOnlySource()
        records = tuple(adapter.read())
        self.assertEqual(records, tuple(adapter.read()))
        self.assertEqual(adapter.source, 'SYNTHETIC_ONLY')
        self.assertEqual(records[0].values['fixture_version'], adapter.version)
        with self.assertRaises(TypeError):
            records[0].values['label'] = 'Forbidden'
        for method in ['write', 'update', 'delete', 'publish']:
            self.assertFalse(hasattr(adapter, method))
