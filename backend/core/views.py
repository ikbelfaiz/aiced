from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import SessionResponseSerializer, ERROR_RESPONSES


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=inline_serializer('Health', {'status': serializers.CharField()}))
    def get(self, request):
        # Liveness only; does not disclose database or infrastructure details.
        return Response({'status': 'ok'})


class SessionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SessionResponseSerializer, **ERROR_RESPONSES})
    def get(self, request):
        return Response(SessionResponseSerializer(request.user).data)
