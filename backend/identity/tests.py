from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import uuid
from django.db import connection, connections, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch
from io import StringIO
from audit.models import AuditEvent
from audit.services import record
from clients.models import Party, PhysicalPerson, LegalEntity, CRMProfile, FinancialAccount
from identity.authentication import consume_login_budget
from identity.models import User, Organization, Membership, Capability, Role, RoleAssignment, LoginBucket


from testing.fixtures import PASSWORD, role, party, SecurityFixtures


class SecurityTests(SecurityFixtures, TestCase):
    def test_anonymous_protected_endpoints(self):
        for url in ['/api/clients/', f'/api/clients/{self.own.pk}/', '/api/audit/', self.assignment_url(),
                    f'/api/organizations/{self.org_a.pk}/users/']:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_list_count_and_detail_scope_assigned_client(self):
        self.login_as(self.reader)
        response = self.client.get('/api/clients/')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['id'], str(self.own.pk))
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/').status_code, 200)
        for target in [self.same_org_hidden.pk, self.other_org_hidden.pk, uuid.uuid4()]:
            self.assertEqual(self.client.get(f'/api/clients/{target}/').status_code, 404)

    def test_client_search_filter_and_pagination_preserve_scope(self):
        self.login_as(self.reader)
        self.assertEqual(self.client.get('/api/clients/', {'search': 'Synthetic hidden'}).json()['count'], 0)
        self.assertEqual(self.client.get('/api/clients/', {'search': str(self.other_org_hidden.pk)}).json()['count'], 0)
        self.assertEqual(self.client.get('/api/clients/', {'search': str(self.own.pk)}).json()['count'], 1)
        self.assertEqual(self.client.get('/api/clients/', {'kind': 'legal'}).json()['count'], 0)
        self.assertEqual(self.client.get('/api/clients/', {'kind': 'unknown'}).status_code, 400)
        self.login_as(self.manager)
        response = self.client.get('/api/clients/', {'page_size': 1})
        self.assertEqual(response.json()['count'], 2)
        self.assertEqual(len(response.json()['results']), 1)
        self.assertIsNotNone(response.json()['next'])
        response = self.client.get('/api/clients/', {'page_size': 1, 'page': 2})
        self.assertEqual(len(response.json()['results']), 1)
        self.assertNotEqual(response.json()['results'][0]['organization_id'], str(self.org_b.pk))

    def test_query_parameters_cannot_expand_scope(self):
        self.login_as(self.reader)
        response = self.client.get('/api/clients/', {'organization_id': self.org_b.pk, 'assigned_to': self.other_m.pk, 'scope': 'organization'})
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['id'], str(self.own.pk))

    def test_forbidden_cross_client_write_has_no_effect(self):
        self.login_as(self.reader)
        for hidden in [self.same_org_hidden, self.other_org_hidden]:
            response = self.client.patch(f'/api/clients/{hidden.pk}/crm/', {'notes': 'Unauthorized'}, format='json')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(CRMProfile.objects.get(party=hidden).notes, '')

    def test_crm_update_is_allowlisted_and_audited_without_notes(self):
        self.login_as(self.reader)
        url = f'/api/clients/{self.own.pk}/crm/'
        for field in ['organization_id', 'assigned_to_id', 'is_superuser', 'accounts', 'source', 'external_id']:
            self.assertEqual(self.client.patch(url, {'notes': 'Synthetic note', field: 'forged'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'notes': 'Synthetic private note'}, format='json').status_code, 200)
        profile = CRMProfile.objects.get(party=self.own)
        self.assertEqual(profile.updated_by, self.reader)
        event = AuditEvent.objects.get(action='clients.crm_updated')
        self.assertEqual(event.target_id, self.own.pk)
        self.assertEqual(event.organization_id, self.org_a.pk)
        self.assertNotIn('Synthetic private note', str(event.__dict__))

    def test_organization_scope_does_not_inherit_children(self):
        self.login_as(self.manager)
        self.assertEqual(self.client.get('/api/clients/').json()['count'], 2)
        self.assertEqual(self.client.get(f'/api/clients/{self.other_org_hidden.pk}/').status_code, 404)

    def test_it_superuser_flags_do_not_grant_client_or_financial_access(self):
        self.login_as(self.it)
        self.assertEqual(self.client.get('/api/clients/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/accounts/').status_code, 403)
        self.assertEqual(self.client.get('/api/audit/').status_code, 403)

    def test_financial_permission_requires_both_object_scopes(self):
        self.login_as(self.reader)
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/accounts/').status_code, 403)
        RoleAssignment.objects.create(membership=self.reader_m, role=self.finance_role, scope='organization')
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/accounts/').json()['count'], 1)
        self.assertEqual(self.client.get(f'/api/clients/{self.same_org_hidden.pk}/accounts/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/clients/{self.other_org_hidden.pk}/accounts/').status_code, 404)

    def test_source_owned_accounts_are_read_only(self):
        self.login_as(self.manager)
        url = f'/api/clients/{self.own.pk}/accounts/'
        self.assertEqual(self.client.post(url, {'source': 'forged'}, format='json').status_code, 405)
        self.assertEqual(self.client.patch(url, {'external_id': 'forged'}, format='json').status_code, 405)

    def test_immediate_revocation_expiration_and_disabled_role(self):
        self.login_as(self.reader)
        self.assertEqual(self.client.get('/api/clients/').status_code, 200)
        for values in [{'is_active': False}, {'is_active': True, 'expires_at': timezone.now() - timedelta(seconds=1)}]:
            RoleAssignment.objects.filter(pk=self.reader_grant.pk).update(**values)
            self.assertEqual(self.client.get('/api/clients/').status_code, 403)
        RoleAssignment.objects.filter(pk=self.reader_grant.pk).update(expires_at=None, is_active=True)
        self.reader_role.is_active = False
        self.reader_role.save()
        self.assertEqual(self.client.get('/api/clients/').status_code, 403)

    def test_inactive_user_membership_and_organization(self):
        self.login_as(self.reader)
        for obj in [self.reader_m, self.org_a, self.reader]:
            obj.is_active = False
            obj.save()
            self.assertEqual(self.client.get('/api/clients/').status_code, 403)
            obj.is_active = True
            obj.save()

    def test_membership_deactivation_is_local_and_audited(self):
        RoleAssignment.objects.create(membership=self.other_b, role=self.reader_role, scope='assigned')
        other_client = APIClient()
        other_client.force_login(self.other)
        self.assertEqual(other_client.get('/api/clients/').json()['count'], 2)
        self.login_as(self.manager)
        url = f'/api/organizations/{self.org_a.pk}/memberships/{self.other_m.pk}/'
        self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 200)
        response = other_client.get('/api/clients/')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['id'], str(self.other_org_hidden.pk))
        event = AuditEvent.objects.get(action='membership.changed')
        self.assertEqual(event.context['after'], {'is_active': False})
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_active)

    def test_user_directory_is_organization_scoped(self):
        self.login_as(self.it)
        url = f'/api/organizations/{self.org_a.pk}/users/'
        self.assertEqual(self.client.get(url).json()['count'], 4)
        self.assertEqual(self.client.get(f'/api/organizations/{self.org_b.pk}/users/').status_code, 403)

    def test_no_role_is_denied_even_for_django_superuser(self):
        user = User.objects.create_superuser('synthetic.breakglass', password=PASSWORD)
        self.login_as(user)
        self.assertEqual(self.client.get('/api/clients/').status_code, 403)
        self.assertEqual(self.client.get(self.assignment_url()).status_code, 403)

    def test_role_changes_require_csrf(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.grant().status_code, 403)

    def test_self_grant_and_self_revocation_are_denied(self):
        self.login_as(self.manager)
        self.assertEqual(self.grant(member=self.manager_m).status_code, 403)
        assignment = RoleAssignment.objects.get(membership=self.manager_m)
        self.assertEqual(self.client.delete(self.assignment_url() + f'{assignment.pk}/').status_code, 403)

    def test_it_cannot_escalate_privileges_or_disable_manager(self):
        self.login_as(self.it)
        self.assertEqual(self.grant(role_obj=self.manager_role, scope='organization').status_code, 403)
        url = f'/api/organizations/{self.org_a.pk}/memberships/{self.manager_m.pk}/'
        self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 403)
        self.manager_m.refresh_from_db()
        self.assertTrue(self.manager_m.is_active)

    def test_admin_urls_and_target_ids_cannot_cross_organizations(self):
        self.login_as(self.manager)
        self.assertEqual(self.client.get(self.assignment_url(self.org_b)).status_code, 403)
        self.assertEqual(self.grant(member=self.other_b).status_code, 404)

    def test_assigned_scope_cannot_be_rebound_to_another_employees_portfolio(self):
        RoleAssignment.objects.create(membership=self.reader_m, role=self.it_role, scope='organization')
        self.login_as(self.reader)
        self.assertEqual(self.grant(scope='organization').status_code, 403)
        self.assertEqual(self.grant(scope='assigned').status_code, 403)

    def test_temporary_admin_cannot_reactivate_permanent_authority(self):
        self.other_m.is_active = False
        self.other_m.save()
        RoleAssignment.objects.filter(membership=self.manager_m).update(expires_at=timezone.now() + timedelta(hours=1))
        self.login_as(self.manager)
        url = f'/api/organizations/{self.org_a.pk}/memberships/{self.other_m.pk}/'
        self.assertEqual(self.client.patch(url, {'is_active': True}, format='json').status_code, 403)
        self.other_m.refresh_from_db()
        self.assertFalse(self.other_m.is_active)

    def test_temporary_authority_cannot_create_permanent_grant(self):
        RoleAssignment.objects.filter(membership=self.manager_m).update(expires_at=timezone.now() + timedelta(hours=1))
        self.login_as(self.manager)
        self.assertEqual(self.grant().status_code, 403)
        self.assertEqual(self.grant(expires_at=(timezone.now() + timedelta(minutes=10)).isoformat()).status_code, 201)

    def test_grant_and_revoke_audited_and_revocation_affects_open_session(self):
        self.login_as(self.manager)
        response = self.grant(member=self.reader_m, role_obj=self.finance_role)
        self.assertEqual(response.status_code, 201)
        grant_id = response.json()['id']
        reader_client = APIClient()
        reader_client.force_login(self.reader)
        self.assertEqual(reader_client.get(f'/api/clients/{self.own.pk}/accounts/').status_code, 200)
        self.assertEqual(self.client.delete(self.assignment_url() + f'{grant_id}/').status_code, 204)
        self.assertEqual(reader_client.get(f'/api/clients/{self.own.pk}/accounts/').status_code, 403)
        self.assertTrue(AuditEvent.objects.filter(action='permissions.granted', target_id=grant_id, actor=self.manager).exists())
        self.assertTrue(AuditEvent.objects.filter(action='permissions.revoked', target_id=grant_id, actor=self.manager).exists())

    def test_user_creation_rejects_privilege_flags_and_weak_password(self):
        self.login_as(self.it)
        url = f'/api/organizations/{self.org_a.pk}/users/'
        base = {'username': 'synthetic.created', 'password': PASSWORD}
        for field in ['is_superuser', 'is_staff', 'groups', 'user_permissions', 'organization_id', 'role_id']:
            self.assertEqual(self.client.post(url, {**base, field: True}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {**base, 'password': '123'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, base, format='json').status_code, 201)
        created = User.objects.get(username=base['username'])
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertFalse(RoleAssignment.objects.filter(membership__user=created).exists())
        self.assertTrue(created.check_password(PASSWORD))
        self.assertTrue(AuditEvent.objects.filter(action='users.created', target_id=created.pk).exists())
        self.assertNotIn('password', str(self.client.get(url).json()))

    def test_audit_access_is_scoped_and_read_only(self):
        record('synthetic.a', organization_id=self.org_a.pk)
        record('synthetic.b', organization_id=self.org_b.pk)
        record('synthetic.global')
        self.login_as(self.manager)
        response = self.client.get('/api/audit/')
        actions = [row['action'] for row in response.json()['results']]
        self.assertEqual(actions, ['synthetic.a'])
        self.assertEqual(self.client.post('/api/audit/', {'action': 'forged'}, format='json').status_code, 405)

    def test_forbidden_requests_are_audited_and_uncacheable(self):
        self.login_as(self.reader)
        response = self.client.get(f'/api/clients/{self.other_org_hidden.pk}/')
        self.assertEqual(response['Cache-Control'], 'no-store')
        event = AuditEvent.objects.get(request_id=response['X-Request-ID'])
        self.assertEqual(event.result, 'denied')
        self.assertEqual(event.actor, self.reader)

    def test_login_csrf_rotation_logout_and_session_invalidation(self):
        self.assertEqual(self.client.post('/api/auth/login/', {'username': self.reader.username, 'password': PASSWORD}, format='json').status_code, 403)
        token = self.client.get('/api/auth/csrf/').json()['csrfToken']
        self.client.credentials(HTTP_X_CSRFTOKEN=token)
        session = self.client.session
        session['synthetic'] = True
        session.save()
        old_key = session.session_key
        self.client.cookies['sessionid'] = old_key
        response = self.client.post('/api/auth/login/', {'username': self.reader.username, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(old_key, self.client.session.session_key)
        self.assertTrue(response.cookies['sessionid']['httponly'])
        self.assertEqual(response.cookies['sessionid']['samesite'], 'Lax')
        from django.contrib.sessions.models import Session
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 403)  # old CSRF token rotated
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.get('/api/auth/csrf/').json()['csrfToken'])
        session_key = self.client.session.session_key
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 204)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        self.assertEqual(self.client.get('/api/session/').status_code, 403)
        for action in ['login.succeeded', 'logout.succeeded']:
            self.assertTrue(AuditEvent.objects.filter(action=action, actor=self.reader).exists())

    @override_settings(LOGIN_ACCOUNT_LIMIT=2, LOGIN_IP_LIMIT=10)
    def test_login_failure_throttle_and_no_credential_logging(self):
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.get('/api/auth/csrf/').json()['csrfToken'])
        data = {'username': self.reader.username, 'password': 'Synthetic-invalid-password'}
        for _ in range(2):
            self.assertEqual(self.client.post('/api/auth/login/', data, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/login/', data, format='json').status_code, 429)
        self.assertEqual(AuditEvent.objects.filter(action='login.failed').count(), 2)
        self.assertTrue(AuditEvent.objects.filter(action='login.throttled').exists())
        for event in AuditEvent.objects.filter(action__startswith='login.'):
            self.assertNotIn(data['username'], str(event.__dict__))
            self.assertNotIn(data['password'], str(event.__dict__))
        self.assertTrue(all(len(key) == 64 for key in LoginBucket.objects.values_list('key', flat=True)))

    def test_inactive_user_cannot_log_in(self):
        self.reader.is_active = False
        self.reader.save()
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.get('/api/auth/csrf/').json()['csrfToken'])
        self.assertEqual(self.client.post('/api/auth/login/', {'username': self.reader.username, 'password': PASSWORD}, format='json').status_code, 400)

    def test_postgres_blocks_cross_org_assignment_and_audit_mutation(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL enforcement')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Party.objects.filter(pk=self.own.pk).update(assigned_to=self.other_b)
        event = record('synthetic.immutable')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(action='forged')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).delete()

    def test_postgres_rejects_wrong_subtype(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL enforcement')
        with self.assertRaises(IntegrityError), transaction.atomic():
            LegalEntity.objects.create(party=self.own, legal_name='Synthetic wrong subtype')
            with connection.cursor() as cursor:
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_postgres_prevents_orphaning_old_subtype_by_reassignment(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL enforcement')
        with self.assertRaises(IntegrityError), transaction.atomic():
            orphan = Party.objects.create(organization=self.org_a, kind='physical', display_name='Synthetic orphan')
            PhysicalPerson.objects.filter(party=self.own).update(party=orphan)

    def test_service_cannot_bypass_scope_without_api(self):
        from clients.services import update_crm
        from django.http import Http404
        from identity.services import assign_role
        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(Http404):
            update_crm(self.reader, self.other_org_hidden.pk, {'notes': 'Forbidden'})
        with self.assertRaises(PermissionDenied):
            assign_role(self.it, self.org_a.pk, {'membership_id': self.other_m.pk, 'role_id': self.manager_role.pk, 'scope': 'organization'})

    def test_audit_failure_rolls_back_mutation(self):
        from clients.services import update_crm
        with patch('clients.services.record', side_effect=RuntimeError('Synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                update_crm(self.reader, self.own.pk, {'notes': 'Must roll back'})
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, '')

    def test_django_global_permissions_and_groups_are_ignored(self):
        from django.contrib.auth.models import Permission, Group
        django_permission = Permission.objects.first()
        self.it.user_permissions.add(django_permission)
        group = Group.objects.create(name='Synthetic global group')
        group.permissions.add(django_permission)
        self.it.groups.add(group)
        self.login_as(self.it)
        self.assertEqual(self.client.get('/api/clients/').status_code, 403)

    def test_role_catalogue_cannot_be_edited_and_omits_non_delegable_roles(self):
        self.login_as(self.it)
        url = f'/api/organizations/{self.org_a.pk}/roles/'
        response = self.client.get(url)
        self.assertEqual([item['id'] for item in response.json()], [str(self.it_role.pk)])
        self.assertEqual(self.client.post(url, {'permissions': ['clients.view_financial']}, format='json').status_code, 405)

    def test_permission_audit_preserves_before_and_after(self):
        self.login_as(self.manager)
        self.assertEqual(self.grant(member=self.reader_m, role_obj=self.finance_role).status_code, 201)
        event = AuditEvent.objects.get(action='permissions.granted')
        self.assertIsNone(event.context['before'])
        self.assertEqual(event.context['after']['permissions'], ['clients.view_financial'])
        self.assertEqual(event.context['after']['membership_id'], str(self.reader_m.pk))

    def test_self_access_discovery_changes_on_revocation(self):
        self.login_as(self.reader)
        response = self.client.get('/api/auth/access/')
        self.assertEqual(len(response.json()['assignments']), 1)
        self.assertEqual(response.json()['assignments'][0]['organization_id'], str(self.org_a.pk))
        RoleAssignment.objects.filter(pk=self.reader_grant.pk).update(is_active=False)
        self.assertEqual(self.client.get('/api/auth/access/').json(), {'assignments': []})

    @override_settings(DEBUG=True)
    def test_synthetic_seed_is_idempotent_and_does_not_reset_passwords(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with patch.dict('os.environ', {'AICED_SEED_PASSWORD': PASSWORD}):
            with self.assertRaises(CommandError):
                call_command('seed_synthetic', stdout=StringIO())
            call_command('seed_synthetic', confirm_synthetic=True, stdout=StringIO())
            counts = (User.objects.count(), Membership.objects.count(), Party.objects.count(), FinancialAccount.objects.count(), RoleAssignment.objects.count())
            user = User.objects.get(username='synthetic.reader.a')
            encoded = user.password
            supervisor = User.objects.get(username='synthetic.supervisor.a')
            supervisor_assignment = RoleAssignment.objects.get(membership__user=supervisor)
            self.assertEqual(supervisor_assignment.scope, 'organization')
            self.assertIn('users.manage', supervisor_assignment.role.permissions.values_list('code', flat=True))
            self.assertIn('clients.view_financial', supervisor_assignment.role.permissions.values_list('code', flat=True))
            call_command('seed_synthetic', confirm_synthetic=True, stdout=StringIO())
            self.assertEqual(counts, (User.objects.count(), Membership.objects.count(), Party.objects.count(), FinancialAccount.objects.count(), RoleAssignment.objects.count()))
            user.refresh_from_db()
            self.assertEqual(user.password, encoded)
            self.assertFalse(Party.objects.exclude(display_name__icontains='Synthetic').exclude(display_name__icontains='SYNTHÉTIQUE').exists())

    @override_settings(DEBUG=False)
    def test_synthetic_seed_refuses_non_debug_environment(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with patch.dict('os.environ', {'AICED_SEED_PASSWORD': PASSWORD}):
            with self.assertRaises(CommandError):
                call_command('seed_synthetic', confirm_synthetic=True, stdout=StringIO())

    @override_settings(LOGIN_ACCOUNT_LIMIT=50, LOGIN_IP_LIMIT=1)
    def test_throttled_ip_cannot_create_unbounded_account_buckets(self):
        self.assertTrue(consume_login_budget('synthetic.first', '192.0.2.1'))
        for i in range(5):
            self.assertFalse(consume_login_budget(f'synthetic.blocked-{i}', '192.0.2.1'))
        self.assertEqual(LoginBucket.objects.count(), 2)

    def test_stale_actor_cannot_use_services_after_global_deactivation(self):
        from clients.services import update_crm
        from django.http import Http404
        User.objects.filter(pk=self.reader.pk).update(is_active=False)
        self.assertTrue(self.reader.is_active)  # Deliberately stale object.
        with self.assertRaises(Http404):
            update_crm(self.reader, self.own.pk, {'notes': 'Forbidden stale actor'})

    def test_direct_service_rejects_oversized_crm_notes(self):
        from clients.services import update_crm
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            update_crm(self.reader, self.own.pk, {'notes': 'x' * 5001})
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, '')

    def test_database_rejects_oversized_crm_notes_even_through_queryset(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CRMProfile.objects.filter(party=self.own).update(notes='x' * 5001)

    def test_failed_logout_does_not_record_success(self):
        self.login_as(self.reader)
        with patch('django.contrib.sessions.backends.db.SessionStore.delete', side_effect=RuntimeError('Synthetic session failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/auth/logout/')
        self.assertFalse(AuditEvent.objects.filter(action='logout.succeeded').exists())

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=256, API_MAX_JSON_BYTES=256)
    def test_json_body_size_is_enforced_before_validation(self):
        self.login_as(self.reader)
        response = self.client.patch(f'/api/clients/{self.own.pk}/crm/', {'notes': 'x' * 512}, format='json')
        self.assertEqual(response.status_code, 413)
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, '')

    def test_auth_schema_declares_actual_response_fields(self):
        from drf_spectacular.generators import SchemaGenerator
        schema = SchemaGenerator().get_schema(request=None, public=True)
        response = schema['paths']['/api/auth/csrf/']['get']['responses']['200']['content']['application/json']['schema']
        self.assertIn('$ref', response)
        component = response['$ref'].split('/')[-1]
        self.assertIn('csrfToken', schema['components']['schemas'][component]['properties'])

    def test_audit_failure_rolls_back_authenticated_session_and_last_login(self):
        from django.contrib.sessions.models import Session
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.get('/api/auth/csrf/').json()['csrfToken'])
        with patch('identity.authentication.record', side_effect=RuntimeError('Synthetic audit failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/auth/login/', {'username': self.reader.username, 'password': PASSWORD}, format='json')
        self.reader.refresh_from_db()
        self.assertIsNone(self.reader.last_login)
        self.assertFalse(any(session.get_decoded().get('_auth_user_id') for session in Session.objects.all()))

    def test_direct_service_rejects_unknown_fields_and_invalid_scope(self):
        from clients.services import update_crm
        from identity.services import assign_role, create_user, set_membership_state
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            update_crm(self.reader, self.own.pk, {'notes': 'Synthetic', 'source': 'forged'})
        with self.assertRaises(ValidationError):
            assign_role(self.manager, self.org_a.pk, {'membership_id': self.other_m.pk, 'role_id': self.reader_role.pk, 'scope': 'global'})
        with self.assertRaises(ValidationError):
            create_user(self.manager, self.org_a.pk, {'username': 'synthetic.forbidden', 'password': PASSWORD, 'is_superuser': True})
        with self.assertRaises(ValidationError):
            set_membership_state(self.manager, self.org_a.pk, self.other_m.pk, {'is_active': 'not-a-boolean'})

    def test_parser_handles_short_reads_without_bypassing_limit(self):
        from io import BytesIO
        from core.parsers import BoundedJSONParser, PayloadTooLarge

        class ShortReads(BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 8))

        stream = ShortReads(b'{}' + b' ' * 1000)
        with override_settings(API_MAX_JSON_BYTES=32):
            with self.assertRaises(PayloadTooLarge):
                BoundedJSONParser().parse(stream)
        self.assertEqual(stream.tell(), 33)

    def test_non_text_charset_is_rejected_without_decompression(self):
        import bz2
        import json
        self.login_as(self.reader)
        body = bz2.compress(json.dumps({'notes': 'Synthetic codec test'}).encode())
        response = self.client.patch(f'/api/clients/{self.own.pk}/crm/', body, content_type='application/json; charset=bz2_codec')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CRMProfile.objects.get(party=self.own).notes, '')

    def test_oversized_accept_parameter_is_rejected(self):
        response = self.client.get('/api/health/', HTTP_ACCEPT='application/json; note="' + ';' * 20000 + '"')
        self.assertEqual(response.status_code, 406)

    def test_invalid_json_and_non_json_have_consistent_errors(self):
        self.login_as(self.reader)
        url = f'/api/clients/{self.own.pk}/crm/'
        for content_type, body, expected in [('application/json', b'{bad', 400), ('text/plain', b'notes=value', 415)]:
            response = self.client.patch(url, body, content_type=content_type)
            self.assertEqual(response.status_code, expected)
            self.assertEqual(response.json()['error']['status'], expected)

    def test_deep_json_is_rejected_as_bad_input(self):
        self.login_as(self.reader)
        body = b'{"notes":' + b'[' * 1200 + b'0' + b']' * 1200 + b'}'
        response = self.client.patch(f'/api/clients/{self.own.pk}/crm/', body, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['status'], 400)

    def test_login_origin_must_match_forwarded_host(self):
        host = 'localhost:5173'
        csrf = self.client.get('/api/auth/csrf/', HTTP_HOST=host).json()['csrfToken']
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf)
        data = {'username': self.reader.username, 'password': PASSWORD}
        self.assertEqual(self.client.post('/api/auth/login/', data, format='json', HTTP_HOST=host,
                                         HTTP_ORIGIN='http://untrusted.example').status_code, 403)
        self.assertEqual(self.client.post('/api/auth/login/', data, format='json', HTTP_HOST=host,
                                         HTTP_ORIGIN='http://localhost:5173').status_code, 200)

    def test_invalid_security_limits_fail_closed(self):
        from config.settings import positive_int_env
        from django.core.exceptions import ImproperlyConfigured
        for value in ['0', '-1', 'invalid']:
            with patch.dict('os.environ', {'LOGIN_WINDOW_SECONDS': value}):
                with self.assertRaises(ImproperlyConfigured):
                    positive_int_env('LOGIN_WINDOW_SECONDS', '900')

    def test_admin_can_revoke_inactive_or_expired_grants_without_financial_access(self):
        self.login_as(self.it)
        expired = RoleAssignment.objects.create(membership=self.other_m, role=self.finance_role, scope='assigned',
                                                expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.delete(self.assignment_url() + f'{expired.pk}/').status_code, 204)
        self.finance_role.is_active = False
        self.finance_role.save()
        disabled = RoleAssignment.objects.create(membership=self.other_m, role=self.finance_role, scope='organization')
        self.assertEqual(self.client.delete(self.assignment_url() + f'{disabled.pk}/').status_code, 204)

    def test_admin_can_disable_membership_with_only_expired_authority(self):
        user = User.objects.create_user('synthetic.expired', password=PASSWORD)
        member = Membership.objects.create(user=user, organization=self.org_a)
        RoleAssignment.objects.create(membership=member, role=self.finance_role, scope='organization',
                                       expires_at=timezone.now() - timedelta(seconds=1))
        self.login_as(self.it)
        url = f'/api/organizations/{self.org_a.pk}/memberships/{member.pk}/'
        self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 200)
        member.refresh_from_db()
        self.assertFalse(member.is_active)


class RevocationRaceTests(TransactionTestCase):
    def test_waiting_crm_write_rechecks_committed_revocation(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL locking')
        from threading import Event
        from time import monotonic, sleep
        from clients.services import update_crm
        from identity.services import revoke_role
        from django.http import Http404
        with transaction.atomic():
            org = Organization.objects.create(code='SYNTHETIC-RACE', name='Synthetic race')
            reader = User.objects.create_user('synthetic.race.reader', password=PASSWORD)
            manager = User.objects.create_user('synthetic.race.manager', password=PASSWORD)
            reader_m = Membership.objects.create(user=reader, organization=org)
            manager_m = Membership.objects.create(user=manager, organization=org)
            reader_role = role('synthetic-race-reader', ['clients.view', 'clients.update_crm'])
            manager_role = role('synthetic-race-manager', ['clients.view', 'clients.update_crm', 'users.manage'])
            grant = RoleAssignment.objects.create(membership=reader_m, role=reader_role, scope='assigned')
            RoleAssignment.objects.create(membership=manager_m, role=manager_role, scope='organization')
            client = party(org, reader_m, 'Synthetic race client')
        ready = Event()
        worker_pid = []

        def write():
            try:
                connection.ensure_connection()
                worker_pid.append(connection.connection.info.backend_pid)
                ready.set()
                try:
                    update_crm(User.objects.get(pk=reader.pk), client.pk, {'notes': 'Must not survive revocation'})
                    return 'updated'
                except Http404:
                    return 'denied'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                Organization.objects.select_for_update().get(pk=org.pk)
                Party.objects.select_for_update().get(pk=client.pk)
                future = executor.submit(write)
                self.assertTrue(ready.wait(5))
                deadline = monotonic() + 5
                blocked = False
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0', [worker_pid[0]])
                        blocked = cursor.fetchone()[0]
                    if blocked or future.done():
                        break
                    sleep(0.01)
                self.assertTrue(blocked, 'The writer must be waiting on a database lock.')
                revoke_role(manager, org.pk, grant.pk)
            self.assertEqual(future.result(timeout=5), 'denied')
        self.assertEqual(CRMProfile.objects.get(party=client).notes, '')


class LoginConcurrencyTests(TransactionTestCase):
    @override_settings(LOGIN_ACCOUNT_LIMIT=5, LOGIN_IP_LIMIT=100)
    def test_concurrent_budget_has_no_lost_increments(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL concurrency')

        def attempt(index):
            try:
                return consume_login_budget('synthetic.concurrent', f'192.0.2.{index}')
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(attempt, range(12)))
        self.assertEqual(sum(results), 5)
        self.assertEqual(LoginBucket.objects.order_by('-attempts').first().attempts, 12)
