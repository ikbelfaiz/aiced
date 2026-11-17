from copy import deepcopy
from unittest.mock import Mock, patch
from django.test import TransactionTestCase
from django.db import transaction
from identity.models import RoleAssignment
from testing.fixtures import SecurityFixtures, role
from internal_api.client import ServiceUnavailable
from integration_service.mapping_examples import preview
from clients.models import Party, ExternalIdentity, FinancialAccount


class SourceMappingTests(SecurityFixtures, TransactionTestCase):
    def setUp(self):
        with transaction.atomic():
            SecurityFixtures.setUpTestData.__func__(type(self))
            self.source_role = role('synthetic-source-review', ['imports.view','clients.view_financial'])
            self.source_grant = RoleAssignment.objects.create(membership=self.reader_m,role=self.source_role,scope='organization')
        SecurityFixtures.setUp(self)

    def url(self, party=None):
        return f'/api/clients/{(party or self.own).pk}/source-mapping-preview/'

    def peer(self, scenario='unique'):
        return Mock(post=Mock(return_value={**preview(scenario),'actor_id':str(self.reader.pk),
            'organization_id':str(self.org_a.pk),'context_party_id':str(self.own.pk)}))

    def test_authorized_preview_no_domain_mutation(self):
        self.login_as(self.reader)
        before=[m.objects.count() for m in [Party,ExternalIdentity,FinancialAccount]]
        with patch('clients.source_mapping.peer',return_value=self.peer()) as factory:
            response=self.client.get(self.url())
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.data['mapping_approved'])
        self.assertEqual(response.data['relationships'][0]['status'],'candidate_unique')
        self.assertEqual(before,[m.objects.count() for m in [Party,ExternalIdentity,FinancialAccount]])
        self.assertEqual(factory.call_count,1)

    def test_visibility_before_peer_and_no_privileged_it(self):
        self.login_as(self.reader)
        with patch('clients.source_mapping.peer') as remote:
            for party in [self.same_org_hidden,self.other_org_hidden]:
                self.assertEqual(self.client.get(self.url(party)).status_code,404)
            remote.assert_not_called()
        self.login_as(self.it)
        with patch('clients.source_mapping.peer') as remote:
            self.assertEqual(self.client.get(self.url()).status_code,403)
            remote.assert_not_called()

    def test_revoked_grant_denies_before_peer(self):
        self.login_as(self.reader)
        RoleAssignment.objects.filter(pk=self.source_grant.pk).update(is_active=False)
        with patch('clients.source_mapping.peer') as remote:
            self.assertEqual(self.client.get(self.url()).status_code,403)
            remote.assert_not_called()

    def test_bad_query_or_real_source_request_never_contacts_peer(self):
        self.login_as(self.reader)
        with patch('clients.source_mapping.peer') as remote:
            for query in ['?mode=published','?scenario=unknown','?scenario=unique&scenario=missing','?source_id=REAL']:
                self.assertEqual(self.client.get(self.url()+query).status_code,400)
            remote.assert_not_called()

    def test_unavailable_peer_and_invalid_or_real_record_fail_closed(self):
        self.login_as(self.reader)
        with patch('clients.source_mapping.peer',return_value=Mock(post=Mock(side_effect=ServiceUnavailable()))):
            self.assertEqual(self.client.get(self.url()).status_code,503)
        for mutate in [lambda d:d.update(mapping_approved=True),lambda d:d.update(context_party_id=str(self.same_org_hidden.pk)),
                       lambda d:d['records'][0].update(source_id='REAL-CUSTOMER-ID'),lambda d:d['records'][0].update(email='private@example.invalid'),
                       lambda d:d.update(real_source_access=True)]:
            remote=self.peer();data=deepcopy(remote.post.return_value);mutate(data);remote.post.return_value=data
            with patch('clients.source_mapping.peer',return_value=remote):
                response=self.client.get(self.url())
                self.assertEqual(response.status_code,503)
                self.assertNotIn('records',response.data)

    def test_all_candidate_cases_remain_unapproved(self):
        self.login_as(self.reader)
        for scenario,status in [('unique','candidate_unique'),('ambiguous','ambiguous_candidate'),('missing','missing_identifier'),
                                ('duplicate','duplicate_identifier'),('multiple_accounts','candidate_unique'),('conflicting_identifiers','conflicting_identifiers')]:
            with patch('clients.source_mapping.peer',return_value=self.peer(scenario)):
                response=self.client.get(self.url()+'?scenario='+scenario)
            self.assertEqual(response.status_code,200,response.data)
            self.assertEqual({x['status'] for x in response.data['relationships']},{status})
            self.assertTrue(all(x['confirmed'] is False for x in response.data['relationships']))

