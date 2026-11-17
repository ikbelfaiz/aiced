"""Isolation gates for the cross-client interaction reader, before its endpoint."""
from datetime import datetime, timezone
from django.test import TestCase
from testing import fixtures
from identity.models import RoleAssignment
from clients.models import Interaction, Prospect


class InteractionHistoryTests(TestCase):
    setUp = fixtures.SecurityFixtures.setUp
    login_as = fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        cls.read_role = fixtures.role('history-reader', ['interactions.view'])
        cls.grant = RoleAssignment.objects.create(membership=cls.reader_m, role=cls.read_role, scope='assigned')
        for party, subject in [(cls.own,'SYNTHETIC visible call'), (cls.same_org_hidden,'SECRET same org'),
                               (cls.other_org_hidden,'SECRET other org')]:
            Interaction.objects.create(party=party, kind='call', subject=subject, notes='Synthetic notes',
                occurred_at=datetime(2026,11,15,23,30,tzinfo=timezone.utc), author=cls.manager)

    def test_counts_search_and_forged_filters_cannot_escape_object_scope(self):
        self.login_as(self.reader)
        data=self.client.get('/api/interactions/').json()
        self.assertEqual(data['count'],1)
        self.assertEqual(data['results'][0]['party_id'],str(self.own.pk))
        for query in ['search=SECRET',f'party_id={self.same_org_hidden.pk}', f'party_id={self.other_org_hidden.pk}',f'author_id={self.other.pk}']:
            response=self.client.get('/api/interactions/?'+query)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['count'],0)

    def test_prospect_scope_is_required_even_through_global_history(self):
        Prospect.objects.create(party=self.own)
        self.login_as(self.reader)
        self.assertEqual(self.client.get('/api/interactions/').json()['count'],0)

    def test_same_object_intersection_not_separate_organization_grants(self):
        self.grant.scope='organization'; self.grant.save()
        self.login_as(self.reader)
        self.assertEqual(self.client.get('/api/interactions/').json()['count'],1)
        self.own.assigned_to=self.other_m; self.own.save()
        self.assertEqual(self.client.get('/api/interactions/').json()['count'],0)

    def test_it_and_anonymous_denied_and_revocation_immediate(self):
        self.assertEqual(self.client.get('/api/interactions/').status_code,403)
        self.login_as(self.it)
        self.assertEqual(self.client.get('/api/interactions/').status_code,403)
        self.login_as(self.reader)
        self.assertEqual(self.client.get('/api/interactions/').status_code,200)
        self.grant.is_active=False; self.grant.save()
        self.assertEqual(self.client.get('/api/interactions/').status_code,403)

    def test_filters_use_tunis_calendar_dates_and_are_validated(self):
        self.login_as(self.reader)
        self.assertEqual(self.client.get('/api/interactions/?date_from=2026-11-16&date_to=2026-11-16&kind=call').json()['count'],1)
        self.assertEqual(self.client.get('/api/interactions/?date_to=2026-11-15').json()['count'],0)
        for query in ['kind=invalid','date_from=bad','party_id=bad','date_from=2026-11-16&date_to=2026-11-15','page_size=0','page=0','search='+('x'*201)]:
            self.assertEqual(self.client.get('/api/interactions/?'+query).status_code,400,query)

    def test_pagination_stable_and_no_finance_or_source_fields(self):
        Interaction.objects.create(party=self.own,kind='email',subject='SYNTHETIC second',notes='',
            occurred_at=datetime(2026,11,15,23,30,tzinfo=timezone.utc),author=self.manager)
        self.login_as(self.reader)
        one=self.client.get('/api/interactions/?page_size=1').json()
        two=self.client.get('/api/interactions/?page_size=1&page=2').json()
        self.assertEqual(one['count'],2)
        self.assertNotEqual(one['results'][0]['id'],two['results'][0]['id'])
        self.assertEqual(set(one['results'][0]),{'id','party_id','party_name','is_prospect','kind','subject','notes','occurred_at','author_id','author_name','version'})
