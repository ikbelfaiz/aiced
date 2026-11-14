from django.urls import path
from ingestion import views

urlpatterns = [
    path("api/imports/context/", views.ImportContextView.as_view()),
    path("api/imports/<uuid:organization_id>/batches/", views.BatchListView.as_view()),
    path("api/imports/<uuid:organization_id>/upload/", views.UploadView.as_view()),
    path(
        "api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/",
        views.BatchView.as_view(),
    ),
    path(
        "api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/rejections/",
        views.RejectionsView.as_view(),
    ),
    path(
        "api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/publish/",
        views.PublishView.as_view(),
    ),
    path("api/imports/<uuid:organization_id>/policies/", views.PoliciesView.as_view()),
    path(
        "api/imports/<uuid:organization_id>/policies/<uuid:policy_id>/approve/",
        views.PolicyApproveView.as_view(),
    ),
    path(
        "api/imports/<uuid:organization_id>/policies/<uuid:policy_id>/revoke/",
        views.PolicyRevokeView.as_view(),
    ),
]
