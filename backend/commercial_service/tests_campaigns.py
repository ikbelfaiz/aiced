from uuid import uuid4
from django.test import SimpleTestCase,override_settings
from rest_framework.exceptions import PermissionDenied
from internal_api.client import ServiceUnavailable
from commercial.campaign_contract import CampaignInput,CampaignFilters
from .campaigns import permissions


class CampaignPolicyTests(SimpleTestCase):
    def data(self):
        a,b=map(str,[uuid4(),uuid4()]);member=str(uuid4())
        return a,b,{'organizations':[{'id':a,'name':'SYNTHETIC A'},{'id':b,'name':'SYNTHETIC B'}],
                    'grants':[{'organization_id':a,'membership_id':member,'scope':'assigned','capability':'opportunities.view'},
                              {'organization_id':b,'membership_id':member,'scope':'organization','capability':'opportunities.manage'}]}

    def test_view_and_manage_must_intersect_on_same_organization(self):
        from uuid import UUID
        a,b,data=self.data()
        self.assertEqual(permissions(data)[0],{UUID(a)})
        self.assertEqual(permissions(data,True)[0],set())
        data['grants'].append({**data['grants'][0],'capability':'opportunities.manage'})
        self.assertEqual(permissions(data,True)[0],{UUID(a)})

    def test_no_implicit_it_or_inactive_grant_fallback(self):
        _,_,data=self.data();data['grants']=[]
        with self.assertRaises(PermissionDenied):permissions(data)
        data['grants']=[{'capability':'users.manage','organization_id':data['organizations'][0]['id'],'membership_id':str(uuid4()),'scope':'organization'}]
        with self.assertRaises(PermissionDenied):permissions(data)

    def test_untrusted_or_malformed_iam_context_fails_closed(self):
        for field,value in [('scope','global'),('organization_id',str(uuid4())),('membership_id','invalid')]:
            _,_,data=self.data();data['grants'][0][field]=value
            with self.assertRaises(ServiceUnavailable):permissions(data)

    def test_no_status_custody_target_execution_or_client_identifiers_in_input(self):
        valid={'name':'SYNTHETIC','organization_id':str(uuid4())}
        for field in ['status','creator_id','owner_id','client_ids','segment_id','recipients','organization_scope','launch']:
            self.assertFalse(CampaignInput(data={**valid,field:'forged'}).is_valid())
        for data in [{'name':''},{'name':'x'*161},{'description':'x'*5001},{'targeting_notes':'x'*2001},{'version':0},{'planned_start':'2026-02-30'}]:
            self.assertFalse(CampaignInput(data={**valid,**data}).is_valid())
        self.assertTrue(CampaignInput(data={'name':'SYNTHETIC','organization_id':str(uuid4()),'planned_start':None,'planned_end':None}).is_valid())

    def test_pagination_and_ordering_are_bounded(self):
        for data in [{'page':0},{'page_size':51},{'ordering':'creator_id'},{'search':'x'*201}]:
            self.assertFalse(CampaignFilters(data=data).is_valid())

    def test_business_date_uses_configured_timezone_not_host_date(self):
        from datetime import datetime,timezone
        from unittest.mock import patch
        from .campaigns import metadata
        with patch('commercial_service.campaigns.timezone.now',return_value=datetime(2031,6,1,0,30,tzinfo=timezone.utc)):
            with override_settings(COMMERCIAL_TIME_ZONE='Africa/Tunis'):
                self.assertEqual(metadata()['business_date'],'2031-06-01')
            with override_settings(COMMERCIAL_TIME_ZONE='America/New_York'):
                self.assertEqual(metadata()['business_date'],'2031-05-31')
