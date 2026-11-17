from django.urls import path
from config.urls import urlpatterns as public
from internal_api.views import ClientAuthorizationView
from clients.pipeline_scope import OpportunityScopeView,CompactOpportunityScopeView

urlpatterns = [
    *public,
    path("internal/v1/clients/authorize", ClientAuthorizationView.as_view()),
    path("internal/v1/clients/opportunity-scope", OpportunityScopeView.as_view()),
    path("internal/v1/clients/opportunity-scope-batch", CompactOpportunityScopeView.as_view()),
]
