from datetime import date, datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, patch
from django.db import transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import ValidationError
from testing.fixtures import SecurityFixtures
from clients.models import Party, SyntheticImportProjection, SyntheticImportJob
from clients.synthetic_imports import apply_page


class SyntheticImportTests(SecurityFixtures, TransactionTestCase):
    def setUp(self):
        with transaction.atomic():
            SecurityFixtures.setUpTestData.__func__(type(self))
        super().setUp()
        self.batch = uuid4()
        self.row_id = uuid4()
        self.date = date(2026, 1, 1)
        self.published = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.rows = [{'row_id': self.row_id, 'source_id': 'TEST-001', 'cells': {'2': 'TEST-001', '4': 'TEST Société'}}]

    def test_replay_update_and_organization_isolation(self):
        apply_page(self.org_a.pk, self.batch, 'legal', self.date, self.published, self.rows)
        item = SyntheticImportProjection.objects.get(source_id='TEST-001')
        party_id = item.party_id
        apply_page(self.org_a.pk, self.batch, 'legal', self.date, self.published, self.rows)
        self.assertEqual(SyntheticImportProjection.objects.count(), 1)
        changed = [{'row_id': uuid4(), 'source_id': 'TEST-001', 'cells': {'2': 'TEST-001', '4': 'TEST Société modifiée'}}]
        apply_page(self.org_a.pk, uuid4(), 'legal', date(2026, 2, 1), self.published, changed)
        item.refresh_from_db()
        self.assertEqual(item.party_id, party_id)
        self.assertEqual(item.cells['4'], 'TEST Société modifiée')
        self.assertEqual(item.party.crm_profile.notes, '')
        apply_page(self.org_b.pk, uuid4(), 'legal', self.date, self.published, self.rows)
        self.assertEqual(SyntheticImportProjection.objects.count(), 2)
        self.assertNotEqual(SyntheticImportProjection.objects.get(organization=self.org_b).party_id, party_id)

    def test_invalid_row_rolls_back_page(self):
        bad = [{'row_id': uuid4(), 'source_id': 'OTHER', 'cells': {'2': 'mismatch'}}]
        with self.assertRaises(ValidationError):
            apply_page(self.org_a.pk, self.batch, 'legal', self.date, self.published, self.rows + bad)
        self.assertFalse(SyntheticImportProjection.objects.exists())

    def test_account_links_by_holder_column_and_rejects_missing_or_ambiguous(self):
        apply_page(self.org_a.pk, self.batch, 'legal', self.date, self.published, self.rows)
        account = [{'row_id': uuid4(), 'source_id': 'TEST-ACCOUNT-1', 'cells': {'4': 'TEST-001', '5': 'TEST-ACCOUNT-1'}}]
        apply_page(self.org_a.pk, uuid4(), 'accounts', self.date, self.published, account)
        party = SyntheticImportProjection.objects.get(template='legal').party
        self.assertEqual(SyntheticImportProjection.objects.get(template='accounts').party_id, party.pk)
        apply_page(self.org_a.pk, uuid4(), 'accounts', self.date, self.published, account)
        self.assertEqual(SyntheticImportProjection.objects.filter(template='accounts').count(), 1)
        missing = [{'row_id': uuid4(), 'source_id': 'TEST-ACCOUNT-2', 'cells': {'4': 'UNKNOWN', '5': 'TEST-ACCOUNT-2'}}]
        with self.assertRaises(ValidationError):
            apply_page(self.org_a.pk, uuid4(), 'accounts', self.date, self.published, missing)
        physical = [{'row_id': uuid4(), 'source_id': 'TEST-001', 'cells': {'2': 'TEST-001', '3': 'TEST'}}]
        with self.assertRaises(ValidationError):
            apply_page(self.org_a.pk, uuid4(), 'physical', self.date, self.published, physical)
        apply_page(self.org_a.pk, uuid4(), 'physical', self.date, self.published, [{'row_id': uuid4(), 'source_id': 'AMBIG', 'cells': {'2': 'AMBIG', '3': 'TEST'}}])
        apply_page(self.org_a.pk, uuid4(), 'legal', self.date, self.published, [{'row_id': uuid4(), 'source_id': 'AMBIG', 'cells': {'2': 'AMBIG', '4': 'TEST'}}])
        ambiguous = [{'row_id': uuid4(), 'source_id': 'TEST-ACCOUNT-3', 'cells': {'4': 'AMBIG', '5': 'TEST-ACCOUNT-3'}}]
        with self.assertRaises(ValidationError):
            apply_page(self.org_a.pk, uuid4(), 'accounts', self.date, self.published, ambiguous)
        self.assertEqual(SyntheticImportProjection.objects.filter(template='accounts').count(), 1)

    @patch('core.synthetic_guard.require_synthetic_database')
    def test_background_discovers_published_batch_and_resumes_idempotently(self, guard):
        from clients.synthetic_worker import run_once
        remote = Mock()
        def post(path, data):
            if path.endswith('discovery'):
                return {'batches': [{'batch_id': str(self.batch), 'organization_id': str(self.org_a.pk), 'template': 'legal'}], 'next_offset': None}
            return {'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch), 'template': 'legal', 'source_as_of': '2026-01-01', 'published_at': '2026-01-02T00:00:00Z', 'offset': 0, 'next_offset': None, 'rows': [{**self.rows[0], 'row_id': str(self.row_id)}]}
        remote.post.side_effect = post
        with patch('clients.synthetic_worker.peer', return_value=remote):
            run_once()
            run_once()
        self.assertEqual(SyntheticImportJob.objects.get(batch_id=self.batch).status, 'complete')
        self.assertEqual(SyntheticImportProjection.objects.filter(source_id='TEST-001').count(), 1)

    @patch('core.synthetic_guard.require_synthetic_database')
    def test_background_retries_after_holder_becomes_available(self, guard):
        from clients.synthetic_worker import run_once
        remote = Mock()
        def post(path, data):
            if path.endswith('discovery'):
                return {'batches': [{'batch_id': str(self.batch), 'organization_id': str(self.org_a.pk), 'template': 'accounts'}], 'next_offset': None}
            return {'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch), 'template': 'accounts', 'source_as_of': '2026-01-01', 'published_at': '2026-01-02T00:00:00Z', 'offset': 0, 'next_offset': None, 'rows': [{'row_id': str(self.row_id), 'source_id': 'TEST-ACCOUNT', 'cells': {'4': 'TEST-001', '5': 'TEST-ACCOUNT'}}]}
        remote.post.side_effect = post
        with patch('clients.synthetic_worker.peer', return_value=remote):
            run_once()
            self.assertEqual(SyntheticImportJob.objects.get(batch_id=self.batch).status, 'blocked')
            self.assertFalse(SyntheticImportProjection.objects.exists())
            apply_page(self.org_a.pk, uuid4(), 'legal', self.date, self.published, self.rows)
            run_once()
        self.assertEqual(SyntheticImportJob.objects.get(batch_id=self.batch).status, 'complete')
        self.assertEqual(SyntheticImportProjection.objects.filter(template='accounts').count(), 1)

    @patch('core.synthetic_guard.require_synthetic_database')
    @override_settings(DEBUG=True)
    def test_unauthorized_user_cannot_sync(self, guard):
        self.login_as(self.it)
        with patch('clients.source_mapping.peer') as remote:
            response = self.client.post('/api/clients/synthetic-import-sync/', {'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch), 'offset': 0}, format='json')
        self.assertEqual(response.status_code, 403)
        remote.assert_not_called()
        self.assertFalse(SyntheticImportProjection.objects.exists())

    @patch('core.synthetic_guard.require_synthetic_database')
    @override_settings(DEBUG=True)
    def test_sync_validates_peer_scope_and_applies_published_rows(self, guard):
        self.login_as(self.manager)
        page = {'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch), 'actor_id': str(self.manager.pk), 'template': 'legal', 'source_as_of': '2026-01-01', 'published_at': '2026-01-02T00:00:00Z', 'offset': 0, 'next_offset': None, 'rows': [{**self.rows[0], 'row_id': str(self.row_id)}]}
        remote = Mock()
        remote.post.return_value = page
        with patch('clients.source_mapping.peer', return_value=remote):
            response = self.client.post('/api/clients/synthetic-import-sync/', {'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(SyntheticImportProjection.objects.filter(organization=self.org_a).count(), 1)
        page['organization_id'] = str(self.org_b.pk)
        with patch('clients.source_mapping.peer', return_value=remote):
            response = self.client.post('/api/clients/synthetic-import-sync/', {'organization_id': str(self.org_a.pk), 'batch_id': str(self.batch)}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(SyntheticImportProjection.objects.filter(organization=self.org_b).exists())
