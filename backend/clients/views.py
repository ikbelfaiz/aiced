from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from identity.policies import grants
from .policies import client_queryset
from .models import FinancialAccount, OperationalAccountProjection
from .serializers import PartySerializer, CRMUpdateSerializer, FinancialAccountSerializer, CRMProfileResponseSerializer, OperationalAccountSerializer
from core.serializers import ERROR_RESPONSES
from .services import update_crm
from .pagination import ClientPagination
from .segmentation import SegmentationFilters, filter_clients


def require_client_permission(user, code):
    if not grants(user, code).exists():
        raise PermissionDenied('Opération non autorisée.')


@extend_schema(parameters=[SegmentationFilters, OpenApiParameter('kind', str, enum=['physical', 'legal'], description='Type de personne ; filtrage dans le périmètre autorisé.')])
class ClientListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartySerializer
    pagination_class = ClientPagination
    filter_backends = [SearchFilter]
    search_fields = ['display_name', 'id']

    def get_queryset(self):
        require_client_permission(self.request.user, 'clients.view')
        queryset = client_queryset(self.request.user, 'clients.view').filter(prospect__isnull=True)
        kind = self.request.query_params.get('kind')
        if kind:
            if kind not in ('physical', 'legal'):
                raise ValidationError({'kind': 'Type de personne non reconnu.'})
            queryset = queryset.filter(kind=kind)
        return filter_clients(queryset,self.request.query_params)


class ClientDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PartySerializer
    lookup_url_kwarg = 'party_id'

    def get_queryset(self):
        require_client_permission(self.request.user, 'clients.view')
        return client_queryset(self.request.user, 'clients.view')


class CRMUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CRMUpdateSerializer, responses={200: CRMProfileResponseSerializer, **ERROR_RESPONSES})
    def patch(self, request, party_id):
        require_client_permission(request.user, 'clients.view')
        require_client_permission(request.user, 'clients.update_crm')
        profile = update_crm(request.user, party_id, request.data, request)
        return Response(CRMProfileResponseSerializer(profile).data)


class AccountListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FinancialAccountSerializer

    def get_queryset(self):
        user = self.request.user
        require_client_permission(user, 'clients.view')
        require_client_permission(user, 'clients.view_financial')
        visible = client_queryset(user, 'clients.view')
        financial = client_queryset(user, 'clients.view_financial').filter(pk__in=visible.values('pk'))
        party = get_object_or_404(financial, pk=self.kwargs['party_id'])
        return FinancialAccount.objects.filter(party=party).order_by('id')


class OperationalAccountListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OperationalAccountSerializer

    def get_queryset(self):
        user = self.request.user
        require_client_permission(user, 'clients.view')
        require_client_permission(user, 'clients.view_financial')
        visible = client_queryset(user, 'clients.view')
        financial = client_queryset(user, 'clients.view_financial').filter(pk__in=visible.values('pk'))
        party = get_object_or_404(financial, pk=self.kwargs['party_id'])
        return OperationalAccountProjection.objects.filter(party=party, organization_id=party.organization_id).order_by('id')
