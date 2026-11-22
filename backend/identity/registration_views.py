from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import consume_login_budget
from .models import RegistrationRequest
from .policies import require
from .registration import (RegistrationSerializer, RegistrationDecisionSerializer,
                           RegistrationItemSerializer, request_registration, review_registration)


class RegistrationResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


@method_decorator(csrf_protect, name='dispatch')
class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=RegistrationSerializer, responses={202: RegistrationResponseSerializer})
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Shared IP budget prevents switching between login and registration to evade it.
        if not consume_login_budget(serializer.validated_data['username'], request.META.get('REMOTE_ADDR', '')):
            raise Throttled(wait=settings.LOGIN_WINDOW_SECONDS)
        request_registration(request.data, request)
        return Response({'detail': 'Si les informations sont recevables, votre demande sera examinée par un responsable de votre institution. Contactez-le par votre canal interne pour le suivi.'}, status=202)


class RegistrationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RegistrationItemSerializer

    def get_queryset(self):
        org = self.kwargs['organization_id']
        require(self.request.user, 'users.manage', org, full_scope=True)
        return RegistrationRequest.objects.filter(organization_id=org, status='pending').select_related('user').order_by('created_at', 'pk')


class RegistrationReviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=RegistrationDecisionSerializer, responses={200: RegistrationItemSerializer})
    def post(self, request, organization_id, registration_id):
        item = review_registration(request.user, organization_id, registration_id, request.data, request)
        return Response(RegistrationItemSerializer(item).data)
