from django.urls import path
from .views import (
    PrincipalView,
    AuthorizationView,
    ClientAuthorizationView,
    AuditView,
    ImportContextView,
    ImportAuditScopeView,
    IntegrationReadyView,
)

urlpatterns = [
    path("internal/v1/principal/resolve", PrincipalView.as_view()),
    path("internal/v1/authorization/check", AuthorizationView.as_view()),
    path("internal/v1/imports/context", ImportContextView.as_view()),
    path("internal/v1/imports/audit-scope", ImportAuditScopeView.as_view()),
    path("internal/v1/integration/ready", IntegrationReadyView.as_view()),
    path("internal/v1/clients/authorize", ClientAuthorizationView.as_view()),
    path("internal/v1/audit/events", AuditView.as_view()),
]
