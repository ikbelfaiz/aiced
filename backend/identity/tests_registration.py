from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditEvent
from identity.models import Membership, RegistrationRequest, User
from testing.fixtures import PASSWORD, SecurityFixtures


class RegistrationTests(SecurityFixtures, TestCase):
    def submit(self, **extra):
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.get('/api/auth/csrf/').json()['csrfToken'])
        return self.client.post('/api/auth/register/', {
            'username': 'synthetic.new', 'email': 'new@example.invalid',
            'password': PASSWORD, 'organization_code': self.org_a.code, **extra,
        }, format='json')

    def review_url(self, item, org=None):
        return f'/api/organizations/{(org or self.org_a).pk}/registrations/{item.pk}/'

    def test_registration_is_inactive_without_membership_or_permissions(self):
        self.assertEqual(self.submit().status_code, 202)
        user = User.objects.get(username='synthetic.new')
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(Membership.objects.filter(user=user).exists())
        self.assertEqual(self.client.post('/api/auth/login/', {'username': user.username, 'password': PASSWORD}, format='json').status_code, 400)
        self.assertEqual(self.client.get('/api/clients/').status_code, 403)
        event = AuditEvent.objects.get(action='registration.requested')
        self.assertNotIn(PASSWORD, str(event.context))
        self.assertNotIn('new@example.invalid', str(event.context))

    def test_csrf_and_unknown_privileged_fields(self):
        self.assertEqual(APIClient(enforce_csrf_checks=True).post('/api/auth/register/', {}, format='json').status_code, 403)
        for field in ['is_active', 'is_staff', 'is_superuser', 'role', 'organization_id']:
            self.assertEqual(self.submit(**{field: True}).status_code, 400)
        self.assertFalse(RegistrationRequest.objects.exists())

    def test_invalid_password_and_username(self):
        self.assertEqual(self.submit(password='1234').status_code, 400)
        self.assertEqual(self.submit(username='invalid space').status_code, 400)

    def test_duplicate_and_unknown_organization_do_not_disclose_existence(self):
        first = self.submit()
        self.assertEqual(self.submit().json(), first.json())
        unknown = self.submit(username='synthetic.unknown', organization_code='NOT-AN-ORG')
        self.assertEqual(unknown.status_code, first.status_code)
        self.assertEqual(unknown.json(), first.json())
        self.assertEqual(RegistrationRequest.objects.count(), 1)

    @override_settings(LOGIN_IP_LIMIT=1)
    def test_registration_is_rate_limited(self):
        self.assertEqual(self.submit().status_code, 202)
        self.assertEqual(self.submit(username='synthetic.second').status_code, 429)

    def test_registration_rollback_if_audit_fails(self):
        with patch('identity.registration.record', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assertFalse(User.objects.filter(username='synthetic.new').exists())

    def test_review_requires_explicit_organization_authority(self):
        self.submit()
        item = RegistrationRequest.objects.get()
        self.assertEqual(self.client.get(f'/api/organizations/{self.org_a.pk}/registrations/').status_code, 403)
        self.login_as(self.reader)
        self.assertEqual(self.client.post(self.review_url(item), {'decision': 'approved'}, format='json').status_code, 403)
        self.login_as(self.it)
        self.assertEqual(self.client.get(f'/api/organizations/{self.org_b.pk}/registrations/').status_code, 403)
        self.assertEqual(self.client.post(self.review_url(item, self.org_b), {'decision': 'approved'}, format='json').status_code, 403)

    def test_cross_organization_object_substitution_is_denied(self):
        self.submit(organization_code=self.org_b.code)
        item = RegistrationRequest.objects.get()
        self.login_as(self.it)
        self.assertEqual(self.client.post(self.review_url(item), {'decision': 'approved'}, format='json').status_code, 404)

    def test_approval_activates_only_a_membership_with_no_grants(self):
        self.submit()
        item = RegistrationRequest.objects.get()
        self.login_as(self.it)
        response = self.client.post(self.review_url(item), {'decision': 'approved'}, format='json')
        self.assertEqual(response.status_code, 200)
        item.user.refresh_from_db()
        self.assertTrue(item.user.is_active)
        self.assertFalse(Membership.objects.get(user=item.user).role_assignments.exists())
        self.login_as(item.user)
        self.assertEqual(self.client.get('/api/auth/access/').json()['assignments'], [])
        self.assertEqual(self.client.get('/api/clients/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/clients/{self.own.pk}/accounts/').status_code, 403)

    def test_rejection_and_repeated_review(self):
        self.submit()
        item = RegistrationRequest.objects.get()
        self.login_as(self.it)
        self.assertEqual(self.client.post(self.review_url(item), {'decision': 'rejected'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(self.review_url(item), {'decision': 'approved'}, format='json').status_code, 400)
        item.user.refresh_from_db()
        self.assertFalse(item.user.is_active)
        self.assertFalse(Membership.objects.filter(user=item.user).exists())

    def test_review_rollback_if_audit_fails(self):
        self.submit()
        item = RegistrationRequest.objects.get()
        self.login_as(self.it)
        with patch('identity.registration.record', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.review_url(item), {'decision': 'approved'}, format='json')
        item.refresh_from_db()
        item.user.refresh_from_db()
        self.assertEqual(item.status, 'pending')
        self.assertFalse(item.user.is_active)
        self.assertFalse(Membership.objects.filter(user=item.user).exists())
