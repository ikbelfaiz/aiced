from datetime import datetime, timezone
from unittest.mock import patch
from django.test import TestCase
from testing import fixtures
from identity.models import RoleAssignment
from clients.models import Prospect


class FollowupTests(TestCase):
    setUp = fixtures.SecurityFixtures.setUp
    login_as = fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        cls.grant = RoleAssignment.objects.create(membership=cls.reader_m,
            role=fixtures.role('followup-reader', ['prospects.view']), scope='assigned')
        for party in [cls.own, cls.same_org_hidden, cls.other_org_hidden]:
            Prospect.objects.create(party=party, next_action='SYNTHETIC follow-up', next_action_date='2026-11-16')

    def get(self, query=''):
        return self.client.get('/api/prospects/follow-ups/?'+query)

    def test_scope_before_counts_and_pages(self):
        self.login_as(self.reader)
        data=self.get().json()
        self.assertEqual(data['count'],1)
        self.assertEqual(sum(data['buckets'].values()),1)
        self.assertEqual(data['results'][0]['id'],str(self.own.pk))
        self.assertEqual(self.get('search='+self.same_org_hidden.display_name).json()['count'],0)
        self.assertEqual(self.get('page_size=1&page=2').status_code,404)

    def test_revocation_it_anonymous_and_capability_intersection(self):
        self.assertEqual(self.get().status_code,403)
        self.login_as(self.it)
        self.assertEqual(self.get().status_code,403)
        self.login_as(self.reader)
        self.assertEqual(self.get().status_code,200)
        self.own.assigned_to=self.other_m; self.own.save()
        self.assertEqual(self.get().json()['count'],0)
        self.grant.is_active=False; self.grant.save()
        self.assertEqual(self.get().status_code,403)

    @patch('django.utils.timezone.now', return_value=datetime(2026,11,15,23,30,tzinfo=timezone.utc))
    def test_business_midnight_buckets_and_inclusive_dates(self, clock):
        self.login_as(self.reader)
        self.assertEqual(self.get().json()['business_date'],'2026-11-16')
        self.assertEqual(self.get('bucket=today').json()['count'],1)
        for date,bucket in [('2026-11-15','overdue'),('2026-11-17','upcoming'),(None,'unscheduled')]:
            Prospect.objects.filter(pk=self.own.pk).update(next_action_date=date)
            self.assertEqual(self.get('bucket='+bucket).json()['count'],1)
        Prospect.objects.filter(pk=self.own.pk).update(next_action_date='2026-11-16', status='closed')
        self.assertEqual(self.get('date_from=2026-11-16&date_to=2026-11-16&status=closed').json()['count'],1)
        self.assertEqual(self.get('status=contact').json()['count'],0)

    def test_validation(self):
        self.login_as(self.reader)
        for query in ['bucket=bad','ordering=bad','status=bad','page=0','page_size=51','date_from=bad',
                      'date_from=2026-11-17&date_to=2026-11-16','search='+('x'*201)]:
            self.assertEqual(self.get(query).status_code,400,query)

    def test_stable_sort_and_no_write(self):
        self.grant.scope='organization'; self.grant.save()
        self.login_as(self.reader)
        # clients.view is still assigned: a broader prospect grant cannot expand it.
        self.assertEqual(self.get('ordering=-next_action_date&page_size=1').json()['count'],1)
        self.assertEqual(self.client.post('/api/prospects/follow-ups/',{},format='json').status_code,405)

    def test_ties_nulls_and_pagination(self):
        self.login_as(self.reader)
        for label,date in [('SYNTHETIC A','2026-11-16'),('SYNTHETIC B',None)]:
            party=fixtures.party(self.org_a,self.reader_m,label)
            Prospect.objects.create(party=party,next_action='',next_action_date=None)
            if date: Prospect.objects.filter(pk=party.pk).update(next_action='Call',next_action_date=date)
        first=self.get('page_size=1').json()
        second=self.get('page_size=1&page=2').json()
        third=self.get('page_size=1&page=3').json()
        self.assertEqual(first['count'],3)
        self.assertEqual(len({row['results'][0]['id'] for row in [first,second,third]}),3)
        self.assertIsNone(third['results'][0]['next_action_date'])
        self.assertEqual(self.get('page_size=1').json()['results'],first['results'])
        self.assertEqual(self.get('ordering=display_name').json()['results'][0]['display_name'],'SYNTHETIC A')
        self.assertEqual(self.get('bucket=unscheduled').json()['count'],1)
        self.assertEqual(self.get('bucket=unscheduled&date_from=2026-01-01').json()['count'],0)
