from django.urls import path
from identity.registration_views import RegisterView, RegistrationListView, RegistrationReviewView
from core.views import SessionView
from identity.views import (
    CsrfView,
    LoginView,
    LogoutView,
    AccessView,
    UserListView,
    MembershipStateView,
    RoleAssignmentView,
    RevokeRoleView,
    RoleCatalogueView,
)
from internal_api.views import (
    PrincipalView,
    AuthorizationView,
    ImportContextView,
    ImportAuditScopeView,
    IntegrationReadyView,
    AuditView,
)
from iam_service.private import (
    GrantSnapshotView,
    ReferenceView,
    JournalView,
    ReadyView,
    RevokeSessionView,
)

urlpatterns = [
    path('api/auth/register/', RegisterView.as_view()),
    path('api/organizations/<uuid:organization_id>/registrations/', RegistrationListView.as_view()),
    path('api/organizations/<uuid:organization_id>/registrations/<uuid:registration_id>/', RegistrationReviewView.as_view()),
    path("api/session/", SessionView.as_view()),
    path("api/auth/csrf/", CsrfView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/access/", AccessView.as_view()),
    path("api/organizations/<uuid:organization_id>/users/", UserListView.as_view()),
    path(
        "api/organizations/<uuid:organization_id>/memberships/<uuid:membership_id>/",
        MembershipStateView.as_view(),
    ),
    path(
        "api/organizations/<uuid:organization_id>/role-assignments/",
        RoleAssignmentView.as_view(),
    ),
    path(
        "api/organizations/<uuid:organization_id>/role-assignments/<uuid:assignment_id>/",
        RevokeRoleView.as_view(),
    ),
    path(
        "api/organizations/<uuid:organization_id>/roles/", RoleCatalogueView.as_view()
    ),
    path("internal/v1/principal/resolve", PrincipalView.as_view()),
    path("internal/v1/authorization/check", AuthorizationView.as_view()),
    path("internal/v1/imports/context", ImportContextView.as_view()),
    path("internal/v1/imports/audit-scope", ImportAuditScopeView.as_view()),
    path("internal/v1/integration/ready", IntegrationReadyView.as_view()),
    path("internal/v1/audit/events", AuditView.as_view()),
    path("internal/v1/sessions/revoke", RevokeSessionView.as_view()),
    path("internal/v1/grants/snapshot", GrantSnapshotView.as_view()),
    path("internal/v1/references/validate", ReferenceView.as_view()),
    path("internal/v1/iam/audit/query", JournalView.as_view()),
    path("health/ready", ReadyView.as_view()),
]
