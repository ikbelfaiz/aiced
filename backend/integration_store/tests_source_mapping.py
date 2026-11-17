from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from integration_service.mapping_examples import preview, SCENARIOS
from integration_service.source_mapping import MappingPreview


class SyntheticMappingTests(SimpleTestCase):
    def payload(self):
        return {'credentials':{'session_key':'a'*32,'method':'GET','host':'gateway:8080','scheme':'http'},
                'actor_id':str(uuid4()),'organization_id':str(uuid4()),'party_id':str(uuid4()),'mode':'synthetic','scenario':'unique'}

    def request(self,data,service='client_crm'):
        from rest_framework.request import Request
        from rest_framework.parsers import JSONParser
        from rest_framework.response import Response
        from rest_framework.exceptions import APIException
        request=Request(APIRequestFactory().post('/internal/v1/source-mapping/preview',data,format='json'),parsers=[JSONParser()])
        view=MappingPreview();view.service=service
        try:
            return view.post(request)
        except APIException as exc:
            return Response({'error':str(exc)},status=exc.status_code)

    def test_deterministic_fixtures_are_detached_and_never_confirmed(self):
        for scenario in SCENARIOS:
            first=preview(scenario);second=preview(scenario)
            self.assertEqual(first,second)
            first['records'][0]['source_id']='MODIFIED'
            self.assertEqual(preview(scenario),second)
            self.assertFalse(second['mapping_approved'])
            self.assertTrue(all(x['confirmed'] is False for x in second['relationships']))

    def test_multiple_accounts_share_one_fictitious_client(self):
        data=preview('multiple_accounts')
        self.assertEqual(len(data['relationships']),2)
        self.assertEqual({tuple(x['fixture_client_candidates']) for x in data['relationships']},{('SYNTH-CRM-P1',)})

    def test_only_client_caller_and_synthetic_mode(self):
        with patch('integration_service.source_mapping.RemoteAccess.authorize') as authorize:
            self.assertEqual(self.request(self.payload(),'commercial').status_code,403)
            data=self.payload();data['mode']='published'
            self.assertEqual(self.request(data).status_code,403)
            authorize.assert_not_called()
            self.assertEqual(self.request(self.payload()).status_code,200)
            self.assertEqual(authorize.call_count,1)

    def test_missing_visibility_or_iam_unavailable_never_returns_records(self):
        from rest_framework.exceptions import PermissionDenied
        from internal_api.client import ServiceUnavailable
        for error in [PermissionDenied(),ServiceUnavailable()]:
            with patch('integration_service.source_mapping.RemoteAccess.authorize',side_effect=error):
                response=self.request(self.payload())
                self.assertIn(response.status_code,[403,503])
                self.assertNotIn('records',response.data)

    def test_unknown_input_and_candidate_names_are_not_queries(self):
        data=self.payload();data['customer_name']='ANY'
        with patch('integration_service.source_mapping.RemoteAccess.authorize') as authorize:
            self.assertEqual(self.request(data).status_code,400)
            authorize.assert_not_called()
