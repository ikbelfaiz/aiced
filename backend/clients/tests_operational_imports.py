from datetime import date, datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, patch

from django.db import transaction
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError
from testing.fixtures import SecurityFixtures
from clients.models import OperationalPersonProjection, OperationalCompanyProjection, OperationalAccountProjection, OperationalImportJob, Party
from clients.operational_imports import apply_physical_page, apply_company_page, apply_account_page


class OperationalImportTests(SecurityFixtures, TransactionTestCase):
    def setUp(self):
        with transaction.atomic():
            SecurityFixtures.setUpTestData.__func__(type(self))
        super().setUp()
        self.batch = uuid4()
        self.when = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.row = {'row_id': uuid4(), 'source_id': 'SYNTH-1', 'cells': {
            '2': 'SYNTH-1', '3': 'Exemple', '4': 'Nadia', '15': 'nadia@example.test', '12': '+21612345678'},
            'normalized_dates': {'9': '2000-01-02'}}

    def apply(self, org, row=None, batch=None, as_of=date(2026, 1, 1)):
        return apply_physical_page(org.pk, batch or self.batch, as_of, self.when, [row or self.row])

    def test_create_replay_and_organization_isolation(self):
        self.assertEqual(self.apply(self.org_a), 1)
        self.assertEqual(self.apply(self.org_a), 0)
        self.assertEqual(self.apply(self.org_b), 1)
        records = OperationalPersonProjection.objects.filter(source_id='SYNTH-1')
        self.assertEqual(records.count(), 2)
        a = records.get(organization_id=self.org_a.pk)
        b = records.get(organization_id=self.org_b.pk)
        self.assertNotEqual(a.party_id, b.party_id)
        self.assertEqual(a.birth_date, date(2000, 1, 2))
        self.assertEqual(a.party.crm_profile.email, 'nadia@example.test')

    def test_excel_datetime_birth_date_creates_client(self):
        row = {**self.row, 'normalized_dates': {'9': '1992-05-14T00:00:00'}}
        self.apply(self.org_a, row)
        self.assertEqual(OperationalPersonProjection.objects.get(organization_id=self.org_a.pk).birth_date, date(1992, 5, 14))

    def test_newer_updates_and_blank_contact_keeps_existing_older_is_ignored(self):
        self.apply(self.org_a)
        newer = {**self.row, 'row_id': uuid4(), 'cells': {**self.row['cells'], '15': '', '12': '+21687654321'}}
        self.apply(self.org_a, newer, uuid4(), date(2026, 2, 1))
        p = OperationalPersonProjection.objects.get(organization_id=self.org_a.pk)
        self.assertEqual(p.party.crm_profile.email, 'nadia@example.test')
        self.assertEqual(p.party.crm_profile.phone, '+21687654321')
        self.assertEqual(self.apply(self.org_a, {**self.row, 'row_id': uuid4()}, uuid4()), 0)
        p.party.crm_profile.refresh_from_db()
        self.assertEqual(p.party.crm_profile.phone, '+21687654321')

    def test_bad_key_rolls_back_whole_page(self):
        invalid = {**self.row, 'row_id': uuid4(), 'source_id': 'OTHER'}
        before = Party.objects.count()
        with self.assertRaises(ValidationError):
            apply_physical_page(self.org_a.pk, self.batch, date(2026, 1, 1), self.when, [self.row, invalid])
        self.assertEqual(Party.objects.count(), before)
        self.assertFalse(OperationalPersonProjection.objects.exists())

    def test_workspace_birth_date_respects_client_and_organization_scope(self):
        self.apply(self.org_a)
        self.apply(self.org_b)
        a = OperationalPersonProjection.objects.get(organization_id=self.org_a.pk)
        b = OperationalPersonProjection.objects.get(organization_id=self.org_b.pk)
        self.login_as(self.manager)
        response = self.client.get(f'/api/clients/{a.party_id}/workspace/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['identity']['birth_date'], '2000-01-02')
        self.assertEqual(self.client.get(f'/api/clients/{b.party_id}/workspace/').status_code, 404)
        self.login_as(self.it)
        self.assertIn(self.client.get(f'/api/clients/{a.party_id}/workspace/').status_code, (403, 404))

    def test_invalid_contact_does_not_create_a_partial_client(self):
        invalid = {**self.row, 'cells': {**self.row['cells'], '15': 'not-an-email'}}
        before = Party.objects.count()
        with self.assertRaises(ValidationError):
            self.apply(self.org_a, invalid)
        self.assertEqual(Party.objects.count(), before)
        self.assertFalse(OperationalPersonProjection.objects.exists())

    def test_missing_names_use_explicit_source_identifier_label(self):
        row = {**self.row, 'cells': {'2': 'SYNTH-1'}, 'normalized_dates': {}}
        self.apply(self.org_a, row)
        person = OperationalPersonProjection.objects.get(organization_id=self.org_a.pk)
        self.assertEqual(person.party.display_name, 'Identifiant source · SYNTH-1')
        self.assertEqual(person.party.physicalperson.first_name, '')
        company_row = {'row_id': uuid4(), 'source_id': 'SYNTH-C', 'cells': {'2': 'SYNTH-C'}, 'normalized_dates': {}}
        apply_company_page(self.org_a.pk, uuid4(), date(2026, 1, 1), self.when, [company_row])
        company = OperationalCompanyProjection.objects.get(organization_id=self.org_a.pk)
        self.assertEqual(company.party.display_name, 'Identifiant source · SYNTH-C')
        self.assertEqual(company.party.legalentity.legal_name, '')

    def test_worker_rejects_wrong_organization_without_writes(self):
        from clients.operational_worker import process
        OperationalImportJob.objects.create(batch_id=self.batch, organization_id=self.org_a.pk)
        remote = Mock()
        remote.post.return_value = {'batch_id': str(self.batch), 'organization_id': str(self.org_b.pk),
            'template': 'physical', 'source_as_of': '2026-01-01', 'published_at': '2026-01-02T00:00:00Z',
            'offset': 0, 'next_offset': None, 'rows': [{**self.row, 'row_id': str(self.row['row_id'])}]}
        with self.assertRaises(ValueError):
            process(remote, self.batch)
        self.assertFalse(OperationalPersonProjection.objects.exists())
        self.assertEqual(OperationalImportJob.objects.get(batch_id=self.batch).processed, 0)

    def test_worker_page_commit_and_replay(self):
        from clients.operational_worker import process
        OperationalImportJob.objects.create(batch_id=self.batch, organization_id=self.org_a.pk)
        remote = Mock()
        remote.post.return_value = {'batch_id': str(self.batch), 'organization_id': str(self.org_a.pk),
            'template': 'physical', 'source_as_of': '2026-01-01', 'published_at': '2026-01-02T00:00:00Z',
            'offset': 0, 'next_offset': None, 'rows': [{**self.row, 'row_id': str(self.row['row_id'])}]}
        process(remote, self.batch)
        process(remote, self.batch)
        self.assertEqual(OperationalPersonProjection.objects.count(), 1)
        self.assertEqual(OperationalImportJob.objects.get(batch_id=self.batch).processed, 1)

    def test_company_key_is_scoped_and_never_merges_with_person(self):
        self.apply(self.org_a)
        row = {'row_id': uuid4(), 'source_id': 'SYNTH-1', 'cells': {'2': 'SYNTH-1', '4': 'SOCIÉTÉ SYNTHÉTIQUE', '7': '+21611111111'}, 'normalized_dates': {}}
        self.assertEqual(apply_company_page(self.org_a.pk, uuid4(), date(2026, 1, 1), self.when, [row]), 1)
        self.assertEqual(apply_company_page(self.org_b.pk, uuid4(), date(2026, 1, 1), self.when, [row]), 1)
        company = OperationalCompanyProjection.objects.get(organization_id=self.org_a.pk)
        self.assertNotEqual(company.party_id, OperationalPersonProjection.objects.get(organization_id=self.org_a.pk).party_id)
        self.assertEqual(company.party.crm_profile.phone, '+21611111111')
        self.assertNotEqual(company.party_id, OperationalCompanyProjection.objects.get(organization_id=self.org_b.pk).party_id)
        self.assertEqual(apply_company_page(self.org_a.pk, uuid4(), date(2026, 1, 1), self.when, [row]), 0)

    def test_company_worker_rejects_template_mismatch(self):
        from clients.operational_worker import process
        OperationalImportJob.objects.create(batch_id=self.batch, organization_id=self.org_a.pk, template='legal')
        remote = Mock()
        remote.post.return_value = {'batch_id': str(self.batch), 'organization_id': str(self.org_a.pk),
            'template': 'physical', 'source_as_of': '2026-01-01', 'published_at': '2026-01-02T00:00:00Z',
            'offset': 0, 'next_offset': None, 'rows': [{**self.row, 'row_id': str(self.row['row_id'])}]}
        with self.assertRaises(ValueError):
            process(remote, self.batch)
        self.assertFalse(OperationalPersonProjection.objects.exists())
        self.assertFalse(OperationalCompanyProjection.objects.exists())

    def test_account_links_only_to_same_organization_physical_holder(self):
        self.apply(self.org_a)
        row = {'row_id': uuid4(), 'source_id': 'SYNTH-ACCOUNT', 'cells': {'4': 'SYNTH-1', '5': 'SYNTH-ACCOUNT'}, 'normalized_dates': {}}
        with self.assertRaises(ValidationError):
            apply_account_page(self.org_b.pk, uuid4(), date(2026, 1, 1), self.when, [row])
        self.assertEqual(apply_account_page(self.org_a.pk, uuid4(), date(2026, 1, 1), self.when, [row]), 1)
        account = OperationalAccountProjection.objects.get()
        self.assertEqual(account.party_id, OperationalPersonProjection.objects.get(organization_id=self.org_a.pk).party_id)
        self.assertEqual(apply_account_page(self.org_a.pk, uuid4(), date(2026, 1, 1), self.when, [row]), 0)
        changed = {**row, 'row_id': uuid4(), 'cells': {'4': 'OTHER', '5': 'SYNTH-ACCOUNT'}}
        with self.assertRaises(ValidationError):
            apply_account_page(self.org_a.pk, uuid4(), date(2026, 2, 1), self.when, [changed])
        self.assertEqual(OperationalAccountProjection.objects.count(), 1)

    def test_account_read_requires_client_and_financial_scope(self):
        self.apply(self.org_a)
        self.apply(self.org_b)
        row = {'row_id': uuid4(), 'source_id': 'SYNTH-ACCOUNT', 'cells': {'4': 'SYNTH-1', '5': 'SYNTH-ACCOUNT'}, 'normalized_dates': {}}
        apply_account_page(self.org_a.pk, uuid4(), date(2026, 1, 1), self.when, [row])
        a = OperationalPersonProjection.objects.get(organization_id=self.org_a.pk)
        b = OperationalPersonProjection.objects.get(organization_id=self.org_b.pk)
        url = f'/api/clients/{a.party_id}/operational-accounts/'
        self.login_as(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['source_id'], 'SYNTH-ACCOUNT')
        self.assertEqual(self.client.get(f'/api/clients/{b.party_id}/operational-accounts/').status_code, 404)
        self.login_as(self.reader)
        self.assertIn(self.client.get(url).status_code, (403, 404))
        self.login_as(self.it)
        self.assertIn(self.client.get(url).status_code, (403, 404))

    @patch('clients.source_mapping.peer')
    def test_job_status_requires_same_organization_and_peer_confirmation(self, peer):
        OperationalImportJob.objects.create(batch_id=self.batch, organization_id=self.org_a.pk, processed=1, status='complete')
        peer.return_value.post.return_value = {'actor_id': str(self.manager.pk), 'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch)}
        self.login_as(self.manager)
        url = f'/api/clients/operational-import-jobs/{self.batch}/?organization_id={self.org_a.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['processed'], 1)
        self.assertIn(self.client.get(f'/api/clients/operational-import-jobs/{self.batch}/?organization_id={self.org_b.pk}').status_code, (403, 404))
        peer.return_value.post.return_value['organization_id'] = str(self.org_b.pk)
        self.assertEqual(self.client.get(url).status_code, 503)
        self.login_as(self.it)
        self.assertIn(self.client.get(url).status_code, (403, 404))
