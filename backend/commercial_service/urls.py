from django.urls import path
from .views import OpportunitiesView, OpportunityDetailView
from .private import JournalView, ready
from .pipeline import PipelineView
from .campaigns import CampaignsView,CampaignContextView,CampaignDetailView

urlpatterns = [
    path('api/campaigns/',CampaignsView.as_view()),
    path('api/campaigns/context/',CampaignContextView.as_view()),
    path('api/campaigns/<uuid:campaign_id>/',CampaignDetailView.as_view()),
    path('api/opportunities/',PipelineView.as_view()),
    path("api/clients/<uuid:party_id>/opportunities/", OpportunitiesView.as_view()),
    path(
        "api/clients/<uuid:party_id>/opportunities/<uuid:activity_id>/",
        OpportunityDetailView.as_view(),
    ),
    path("internal/v1/commercial/audit/query", JournalView.as_view()),
    path("health/ready", ready),
]
