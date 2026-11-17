from unittest.mock import patch
from django.test import TestCase,override_settings
from testing import fixtures
from identity.models import RoleAssignment


class AgendaTests(TestCase):
    setUp=fixtures.SecurityFixtures.setUp
    login_as=fixtures.SecurityFixtures.login_as
    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        role=fixtures.role('agenda-operator',['interactions.view','interactions.manage'])
        cls.assignment=RoleAssignment.objects.create(membership=cls.reader_m,role=role,scope='assigned')
        RoleAssignment.objects.create(membership=cls.other_m,role=role,scope='organization')

    def payload(self,**extra):
        return {'organization_id':str(self.org_a.pk),'title':'SYNTHETIC appointment','kind':'meeting','date':'2026-11-17','start_time':'10:00','end_time':'11:00',**extra}
    def create(self,**extra):return self.client.post('/api/agenda/',self.payload(**extra),format='json')

    def test_creation_editing_timezone_and_stale_version(self):
        self.login_as(self.reader)
        response=self.create();self.assertEqual(response.status_code,201)
        from datetime import datetime,timezone
        item=response.json();self.assertEqual(datetime.fromisoformat(item['starts_at']).astimezone(timezone.utc).hour,9)
        url='/api/agenda/'+item['id']+'/'
        self.assertEqual(self.client.patch(url,{'version':1,'title':'SYNTHETIC edited'},format='json').status_code,200)
        self.assertEqual(self.client.patch(url,{'version':1,'title':'stale'},format='json').status_code,409)
        self.assertEqual(self.client.get('/api/agenda/?month=2026-11').json()['days'],{'2026-11-17':1})

    def test_owner_only_before_counts_days_search_and_guessed_ids(self):
        self.login_as(self.other);hidden=self.create(title='SECRET same organization').json()['id']
        self.login_as(self.reader)
        data=self.client.get('/api/agenda/?month=2026-11').json()
        self.assertEqual(data['count'],0);self.assertEqual(data['days'],{})
        for method in ['get','patch']:
            response=getattr(self.client,method)('/api/agenda/'+hidden+'/',*([{'version':1,'title':'forged'}] if method=='patch' else []),format='json')
            self.assertEqual(response.status_code,404)
        self.assertEqual(self.client.get('/api/agenda/?month=2026-11&search=SECRET').json()['count'],0)

    def test_denied_revoked_cross_org_and_owner_assignment(self):
        self.assertEqual(self.client.get('/api/agenda/').status_code,403)
        self.login_as(self.it);self.assertEqual(self.create().status_code,403)
        self.login_as(self.reader)
        self.assertEqual(self.create(organization_id=str(self.org_b.pk)).status_code,403)
        self.assertEqual(self.create(owner_id=str(self.other.pk)).status_code,400)
        self.assignment.is_active=False;self.assignment.save()
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.client.get('/api/agenda/').status_code,403)

    def test_time_validation_overlaps_allowed_and_pages(self):
        self.login_as(self.reader)
        for extra in [{'end_time':'10:00'},{'end_time':'09:00'},{'date':'bad'},{'start_time':'10:00Z'},{'date':'9999-12-31'}]:
            self.assertEqual(self.create(**extra).status_code,400,extra)
        for extra in [{},{'start_time':'10:30','end_time':'11:30'},{'start_time':'11:30','end_time':'12:00'}]:self.assertEqual(self.create(**extra).status_code,201)
        first=self.client.get('/api/agenda/?month=2026-11&page_size=1').json()
        second=self.client.get('/api/agenda/?month=2026-11&page_size=1&page=2').json()
        self.assertEqual(first['count'],3);self.assertNotEqual(first['results'][0]['id'],second['results'][0]['id'])
        self.assertEqual(self.client.get('/api/agenda/?month=2026-11&day=2026-11-18').json()['count'],0)
        for query in ['month=bad','month=2026-11&day=2026-12-01','page_size=51','page=0']:
            self.assertEqual(self.client.get('/api/agenda/?'+query).status_code,400)

    @override_settings(AICED_AGENDA_TIME_ZONE='America/New_York')
    def test_dst_ambiguity_and_nonexistent_times_rejected(self):
        self.login_as(self.reader)
        for values in [{'date':'2026-03-08','start_time':'02:30','end_time':'04:00'},{'date':'2026-11-01','start_time':'01:30','end_time':'03:00'}]:
            self.assertEqual(self.create(**values).status_code,400)

    def test_audit_outbox_failure_rolls_back_and_immutable_scope(self):
        from clients.models import Appointment
        self.login_as(self.reader)
        with patch('audit.services.AuditOutbox.objects.create',side_effect=RuntimeError('synthetic outbox failure')):
            with self.assertRaises(RuntimeError):self.create()
        self.assertEqual(Appointment.objects.count(),0)
        item=self.create().json()
        self.assertEqual(self.client.patch('/api/agenda/'+item['id']+'/',{'version':1,'organization_id':str(self.org_a.pk)},format='json').status_code,400)
