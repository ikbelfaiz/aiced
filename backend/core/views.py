from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.http import FileResponse, Http404
from .serializers import SessionResponseSerializer, ERROR_RESPONSES


class SPAView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        index = settings.BASE_DIR / 'frontend_dist' / 'index.html'
        if not index.is_file():
            raise Http404
        return FileResponse(index.open('rb'), content_type='text/html')


class FrontendAssetView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, path):
        assets = (settings.BASE_DIR / 'frontend_dist' / 'assets').resolve()
        asset = (assets / path).resolve()
        if not asset.is_relative_to(assets) or not asset.is_file():
            raise Http404
        import mimetypes
        content_type = mimetypes.guess_type(asset.name)[0] or 'application/octet-stream'
        return FileResponse(asset.open('rb'), content_type=content_type)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=inline_serializer('Health', {'status': serializers.CharField()}))
    def get(self, request):
        # Liveness only; does not disclose database or infrastructure details.
        return Response({'status': 'ok'})


class SessionView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: SessionResponseSerializer, **ERROR_RESPONSES})
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {'error': {'status': 403, 'details': 'Session not authenticated.'}},
                status=403,
            )
        return Response(SessionResponseSerializer(request.user).data)
