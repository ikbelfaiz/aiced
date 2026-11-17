from datetime import datetime,date,timezone as utc,timedelta
from unittest.mock import patch
from django.test import TransactionTestCase,override_settings
from django.db import transaction
from clients.models import Interaction,Appointment,Prospect
from testing import fixtures
from identity.models import RoleAssignment

class ReportingTests(TransactionTestCase):
    login_as=fixtures.SecurityFixtures.login_as

    def setUp(self):
        with transaction.atomic():
            fixtures.SecurityFixtures.setUpTestData.__func__(type(self))
        fixtures.SecurityFixtures.setUp(self)
        self.extra=RoleAssignment.objects.create(membership=self.reader_m,role=fixtures.role('SYNTHETIC reporting',['interactions.view','prospects.view']),scope='assigned')
        for party in [self.own,self.same_org_hidden,self.other_org_hidden]:
            for value,kind in [('2026-11-14T22:59:59+00:00','visit'),('2026-11-14T23:00:00+00:00','call'),('2026-11-15T22:59:59+00:00','email'),('2026-11-15T23:00:00+00:00','visit')]:
                Interaction.objects.create(party=party,author=self.reader,kind=kind,subject='SYNTHETIC report',occurred_at=datetime.fromisoformat(value))
            Prospect.objects.create(party=party,next_action='SYNTHETIC',next_action_date=date(2026,11,15))
        Appointment.objects.create(owner=self.reader,organization=self.org_a,title='SYNTHETIC own',kind='meeting',starts_at=datetime(2026,11,14,23,tzinfo=utc.utc),ends_at=datetime(2026,11,15,0,tzinfo=utc.utc))
        Appointment.objects.create(owner=self.other,organization=self.org_a,title='SYNTHETIC hidden',kind='call',starts_at=datetime(2026,11,15,10,tzinfo=utc.utc),ends_at=datetime(2026,11,15,11,tzinfo=utc.utc))

    def get(self,query='date_from=2026-11-15&date_to=2026-11-15'):
        return self.client.get('/api/clients/activity-report/?'+query)

    def test_exact_counts_midnight_and_owner_only(self):
        self.login_as(self.reader)
        data=self.get().json()
        self.assertEqual(data['interactions']['total'],2)
        self.assertEqual(data['interactions']['by_kind'],{'call':1,'email':1,'meeting':0,'visit':0})
        self.assertEqual(data['interactions']['daily'],[{'date':'2026-11-15','count':2}])
        self.assertEqual(data['appointments']['total'],1)
        self.assertEqual(sum(data['followups'].values()),1)
        self.assertNotIn('SYNTHETIC hidden',str(data))

    def test_kind_filter_only_affects_period_metrics(self):
        self.login_as(self.reader)
        a=self.get().json();b=self.get('date_from=2026-11-15&date_to=2026-11-15&kind=call').json()
        self.assertEqual(b['interactions']['total'],1)
        self.assertEqual(b['appointments']['total'],0)
        self.assertEqual(a['followups'],b['followups'])

    @patch('django.utils.timezone.now',return_value=datetime(2026,11,15,23,30,tzinfo=utc.utc))
    def test_business_today_and_current_closed_followups(self,clock):
        self.login_as(self.reader)
        Prospect.objects.filter(pk=self.own.pk).update(status='closed')
        data=self.get().json()
        self.assertEqual(data['business_date'],'2026-11-16')
        self.assertEqual(data['followups'],{'overdue':1,'today':0,'upcoming':0,'unscheduled':0})
        defaults=self.get('').json()
        self.assertEqual((defaults['date_from'],defaults['date_to']),('2026-10-18','2026-11-16'))

    def test_permissions_before_aggregates_and_partial_availability(self):
        self.assertEqual(self.get().status_code,403)
        self.login_as(self.it);self.assertEqual(self.get().status_code,403)
        self.login_as(self.reader)
        self.extra.role.permissions.remove('interactions.view')
        data=self.get().json()
        self.assertIsNone(data['interactions']);self.assertIsNone(data['appointments'])
        self.assertEqual(sum(data['followups'].values()),1)
        self.extra.is_active=False;self.extra.save()
        self.assertEqual(self.get().status_code,403)

    def test_reassignment_empty_period_and_validation(self):
        self.login_as(self.reader)
        self.own.assigned_to=self.other_m;self.own.save()
        data=self.get().json()
        self.assertEqual(data['interactions']['total'],0)
        self.assertEqual(sum(data['followups'].values()),0)
        self.assertEqual(self.get('date_from=2025-01-01&date_to=2025-01-01').json()['appointments']['total'],0)
        for query in ['kind=bad','date_from=bad','date_from=2026-01-02&date_to=2026-01-01','date_from=2026-01-01&date_to=2026-04-04','date_to=9999-12-31']:
            self.assertEqual(self.get(query).status_code,400,query)
        self.assertEqual(len(self.get('date_from=2026-01-01&date_to=2026-04-03').json()['interactions']['daily']),93)

    @override_settings(AICED_REPORT_TIME_ZONE='America/New_York')
    def test_configurable_zone_dst_day(self):
        self.login_as(self.reader)
        for stamp in ['2026-03-08T04:59:59+00:00','2026-03-08T05:00:00+00:00','2026-03-09T03:59:59+00:00','2026-03-09T04:00:00+00:00']:
            Interaction.objects.create(party=self.own,author=self.reader,kind='call',subject='SYNTHETIC DST',occurred_at=datetime.fromisoformat(stamp))
        data=self.get('date_from=2026-03-08&date_to=2026-03-08').json()
        self.assertEqual(data['interactions']['total'],2)
        self.assertEqual(data['business_timezone'],'America/New_York')

    def test_bound_timeout_and_expired_session(self):
        self.login_as(self.reader)
        with patch('clients.reporting.monotonic',side_effect=[0,5]):
            self.assertEqual(self.get().status_code,503)
        from django.contrib.sessions.models import Session
        Session.objects.filter(session_key=self.client.session.session_key).update(expire_date=datetime.now(utc.utc)-timedelta(days=1))
        self.assertEqual(self.get().status_code,403)

    def test_scope_commit_between_admission_locks_cannot_use_old_snapshot(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connection,connections
        from core.admission import AUTH_BARRIER
        from core.client_admission import CLIENT_SCOPE_BARRIER
        from clients.models import Party
        self.login_as(self.reader)
        changed=False
        def reassign():
            try:
                with transaction.atomic():
                    with connections['default'].cursor() as cursor:
                        cursor.execute('SELECT pg_advisory_xact_lock_shared(%s)',[AUTH_BARRIER])
                        cursor.execute('SELECT pg_advisory_xact_lock(%s)',[CLIENT_SCOPE_BARRIER])
                    Party.objects.filter(pk=self.own.pk).update(assigned_to_id=self.other_m.pk)
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            def execute(executor,sql,params,many,context):
                nonlocal changed
                result=executor(sql,params,many,context)
                if not changed and sql.startswith('SELECT pg_try_advisory_xact_lock_shared') and params==[AUTH_BARRIER]:
                    changed=True
                    pool.submit(reassign).result(timeout=3)
                return result
            with connection.execute_wrapper(execute):data=self.get().json()
        self.assertTrue(changed)
        self.assertEqual(data['interactions']['total'],0)
        self.assertEqual(sum(data['followups'].values()),0)
