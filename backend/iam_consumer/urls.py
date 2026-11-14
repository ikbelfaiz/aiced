from django.urls import path
from config.urls import urlpatterns as public
from internal_api.views import ClientAuthorizationView

urlpatterns = [
    *public,
    path("internal/v1/clients/authorize", ClientAuthorizationView.as_view()),
]
