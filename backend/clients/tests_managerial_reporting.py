from datetime import date,datetime,timezone
from unittest.mock import patch
from django.test import TransactionTestCase,override_settings
from django.db import transaction
from clients.models import CRMProfile,Interaction,Prospect,Appointment
from identity.models import RoleAssignment,Membership
from testing import fixtures


class ManagerialReportingTests(TransactionTestCase):
    login_as=fixtures.SecurityFixtures.login_as

    def setUp(self):
        with transaction.atomic():
            fixtures.SecurityFixtures.setUpTestData.__func__(type(self))
        fixtures.SecurityFixtures.setUp(self)

    def get(self,query='date_from=2024-06-19&date_to=2024-06-19'):
        return self.client.get('/api/clients/managerial-report/?'+query)

    def test_assigned_and_organization_scope_before_portfolio_and_quality(self):
        self.login_as(self.reader)
        data=self.get().json()
        self.assertEqual(data['portfolio']['quality']['total'],1)
        self.assertEqual(data['portfolio']['by_kind'],{'physical':1,'legal':0})
        self.assertEqual(data['portfolio']['quality']['missing_counts'],dict.fromkeys(['email','phone','profession','sector'],1))
        self.assertIsNone(data['interactions']);self.assertIsNone(data['followups']);self.assertIsNone(data['appointments'])
        self.login_as(self.manager)
        self.assertEqual(self.get().json()['portfolio']['quality']['total'],2)
        # reports.view_global never grants object visibility or extra organizations.
        RoleAssignment.objects.create(membership=self.reader_m,role=fixtures.role('SYNTHETIC report-only',['reports.view_global']),scope='organization')
        self.login_as(self.reader)
        self.assertEqual(self.get().json()['portfolio']['quality']['total'],1)

    def test_exact_completeness_whitespace_hidden_rows_and_missing_definition(self):
        self.login_as(self.reader)
        CRMProfile.objects.filter(party=self.same_org_hidden).update(email='hidden@example.invalid',phone='hidden',profession='hidden',sector='hidden')
        CRMProfile.objects.filter(party=self.own).update(email=' \t ',phone='SYNTHETIC',profession='',sector='SYNTHETIC')
        quality=self.get().json()['portfolio']['quality']
        self.assertEqual((quality['complete'],quality['incomplete']),(0,1))
        self.assertEqual(quality['missing_counts'],{'email':1,'phone':0,'profession':1,'sector':0})
        CRMProfile.objects.filter(party=self.own).update(email='test@example.invalid',profession='SYNTHETIC')
        self.assertEqual(self.get().json()['portfolio']['quality']['complete'],1)
        with patch.dict('os.environ',{'AICED_PROFILE_COMPLETENESS_FIELDS':''}):
            quality=self.get().json()['portfolio']['quality']
            self.assertFalse(quality['available']);self.assertIsNone(quality['complete'])

    def test_disjoint_organization_capabilities_do_not_enable_activity_or_deny_portfolio(self):
        member=Membership.objects.create(user=self.reader,organization=self.org_b)
        RoleAssignment.objects.create(membership=member,role=fixtures.role('SYNTHETIC disjoint activities',['interactions.view','prospects.view']),scope='organization')
        self.login_as(self.reader)
        response=self.get()
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['portfolio']['quality']['total'],1)
        self.assertIsNone(data['interactions']);self.assertIsNone(data['appointments']);self.assertIsNone(data['followups'])

    def test_prospect_exclusion_period_midnight_and_owner_only_appointments(self):
        RoleAssignment.objects.create(membership=self.reader_m,role=fixtures.role('SYNTHETIC activities',['interactions.view','prospects.view']),scope='assigned')
        Prospect.objects.create(party=self.own,next_action='SYNTHETIC',next_action_date=date(2024,6,19))
        for party in [self.own,self.same_org_hidden,self.other_org_hidden]:
            for stamp in ['2024-06-18T22:59:59Z','2024-06-18T23:00:00Z','2024-06-19T22:59:59Z','2024-06-19T23:00:00Z']:
                Interaction.objects.create(party=party,author=self.reader,kind='call',subject='SYNTHETIC',occurred_at=datetime.fromisoformat(stamp))
        for owner in [self.reader,self.other]:
            Appointment.objects.create(owner=owner,organization=self.org_a,title='SYNTHETIC',kind='meeting',starts_at=datetime(2024,6,19,10,tzinfo=timezone.utc),ends_at=datetime(2024,6,19,11,tzinfo=timezone.utc))
        self.login_as(self.reader)
        data=self.get().json()
        self.assertEqual(data['portfolio']['quality']['total'],0)
        self.assertEqual(data['interactions']['total'],2)
        self.assertEqual(data['interactions']['daily'],[{'date':'2024-06-19','count':2}])
        self.assertEqual(data['appointments']['total'],1)
        self.assertEqual(sum(data['followups'].values()),1)
        self.assertEqual(self.get('date_from=2024-06-19&date_to=2024-06-19&kind=email').json()['interactions']['total'],0)

    def test_empty_visibility_and_revocation_denies_instead_of_leaking_counts(self):
        self.assertEqual(self.get().status_code,403)
        self.login_as(self.it);self.assertEqual(self.get().status_code,403)
        self.login_as(self.reader)
        self.own.assigned_to=self.other_m;self.own.save()
        data=self.get().json()
        self.assertEqual(data['portfolio']['quality']['total'],0)
        self.assertEqual(data['portfolio']['quality']['complete'],0)
        self.reader_grant.is_active=False;self.reader_grant.save()
        response=self.get()
        self.assertEqual(response.status_code,403);self.assertNotIn('portfolio',response.json())

    def test_validation_budget_and_read_only(self):
        from audit.models import AuditEvent,AuditOutbox
        self.login_as(self.reader)
        before=(AuditEvent.objects.count(),AuditOutbox.objects.count(),CRMProfile.objects.count())
        self.assertEqual(self.get().status_code,200)
        self.assertEqual(before,(AuditEvent.objects.count(),AuditOutbox.objects.count(),CRMProfile.objects.count()))
        for query in ['kind=invalid','date_from=2024-06-20&date_to=2024-06-19','date_from=2024-01-01&date_to=2024-06-01']:
            self.assertEqual(self.get(query).status_code,400)
        with patch('clients.reporting.monotonic',side_effect=[0,5]):
            response=self.get()
            self.assertEqual(response.status_code,503);self.assertNotIn('portfolio',response.json())
        self.assertEqual(self.client.post('/api/clients/managerial-report/',{},format='json').status_code,405)
