from django.urls import path
from .views import OpportunitiesView, OpportunityDetailView
from .private import JournalView, ready

urlpatterns = [
    path("api/clients/<uuid:party_id>/opportunities/", OpportunitiesView.as_view()),
    path(
        "api/clients/<uuid:party_id>/opportunities/<uuid:activity_id>/",
        OpportunityDetailView.as_view(),
    ),
    path("internal/v1/commercial/audit/query", JournalView.as_view()),
    path("health/ready", ready),
]
