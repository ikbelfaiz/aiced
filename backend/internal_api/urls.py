from django.urls import path
from .views import (
    PrincipalView,
    AuthorizationView,
    ClientAuthorizationView,
    AuditView,
    ImportContextView,
)

urlpatterns = [
    path("internal/v1/principal/resolve", PrincipalView.as_view()),
    path("internal/v1/authorization/check", AuthorizationView.as_view()),
    path("internal/v1/imports/context", ImportContextView.as_view()),
    path("internal/v1/clients/authorize", ClientAuthorizationView.as_view()),
    path("internal/v1/audit/events", AuditView.as_view()),
]
