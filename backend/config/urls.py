from django.urls import path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.permissions import IsAuthenticated
from core.views import HealthView, SessionView
from identity.views import (CsrfView, LoginView, LogoutView, AccessView, UserListView,
                            MembershipStateView, RoleAssignmentView, RevokeRoleView, RoleCatalogueView)
from clients.views import ClientListView, ClientDetailView, CRMUpdateView, AccountListView
from audit.views import AuditListView
from clients.prospects import ProspectsView, ProspectView, ProspectContextView
from clients.workspace_views import WorkspaceView, CreatePartyView, IdentityEditView, ProfileView, ActivityView, OpportunitiesView, ClientContextView, InteractionDetailView, OpportunityDetailView
from ingestion.views import ImportContextView, BatchListView, UploadView, BatchView, RejectionsView, PoliciesView, PolicyApproveView, PolicyRevokeView, PublishView

urlpatterns = [
    path('api/prospects/', ProspectsView.as_view()),
    path('api/prospects/context/', ProspectContextView.as_view()),
    path('api/prospects/<uuid:party_id>/', ProspectView.as_view()),
    path('api/imports/context/',ImportContextView.as_view()),
    path('api/imports/<uuid:organization_id>/batches/',BatchListView.as_view()),
    path('api/imports/<uuid:organization_id>/upload/',UploadView.as_view()),
    path('api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/',BatchView.as_view()),
    path('api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/rejections/',RejectionsView.as_view()),
    path('api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/publish/',PublishView.as_view()),
    path('api/imports/<uuid:organization_id>/policies/',PoliciesView.as_view()),
    path('api/imports/<uuid:organization_id>/policies/<uuid:policy_id>/approve/',PolicyApproveView.as_view()),
    path('api/imports/<uuid:organization_id>/policies/<uuid:policy_id>/revoke/',PolicyRevokeView.as_view()),
    path('api/health/', HealthView.as_view(), name='health'),
    path('api/session/', SessionView.as_view(), name='session'),
    path('api/schema/', SpectacularAPIView.as_view(permission_classes=[IsAuthenticated]), name='schema'),
    path('api/auth/csrf/', CsrfView.as_view()),
    path('api/auth/login/', LoginView.as_view()),
    path('api/auth/logout/', LogoutView.as_view()),
    path('api/auth/access/', AccessView.as_view()),
    path('api/clients/', ClientListView.as_view()),
    path('api/clients/create/', CreatePartyView.as_view()),
    path('api/clients/context/', ClientContextView.as_view()),
    path('api/clients/<uuid:party_id>/workspace/', WorkspaceView.as_view()),
    path('api/clients/<uuid:party_id>/identity/', IdentityEditView.as_view()),
    path('api/clients/<uuid:party_id>/profile/', ProfileView.as_view()),
    path('api/clients/<uuid:party_id>/interactions/', ActivityView.as_view()),
    path('api/clients/<uuid:party_id>/interactions/<uuid:activity_id>/', InteractionDetailView.as_view()),
    path('api/clients/<uuid:party_id>/opportunities/', OpportunitiesView.as_view()),
    path('api/clients/<uuid:party_id>/opportunities/<uuid:activity_id>/', OpportunityDetailView.as_view()),
    path('api/clients/<uuid:party_id>/', ClientDetailView.as_view()),
    path('api/clients/<uuid:party_id>/crm/', CRMUpdateView.as_view()),
    path('api/clients/<uuid:party_id>/accounts/', AccountListView.as_view()),
    path('api/organizations/<uuid:organization_id>/users/', UserListView.as_view()),
    path('api/organizations/<uuid:organization_id>/memberships/<uuid:membership_id>/', MembershipStateView.as_view()),
    path('api/organizations/<uuid:organization_id>/role-assignments/', RoleAssignmentView.as_view()),
    path('api/organizations/<uuid:organization_id>/role-assignments/<uuid:assignment_id>/', RevokeRoleView.as_view()),
    path('api/organizations/<uuid:organization_id>/roles/', RoleCatalogueView.as_view()),
    path('api/audit/', AuditListView.as_view()),
]
