"""Client-owned, scoped interaction history; no finance or peer ORM access."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from identity.policies import organization_ids
from .models import Interaction
from .policies import client_queryset
from .pagination import ClientPagination


class HistoryFilters(serializers.Serializer):
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=['call','email','meeting','visit'], required=False, allow_blank=True)
    party_id = serializers.UUIDField(required=False)
    author_id = serializers.UUIDField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False)

    def validate(self, data):
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise serializers.ValidationError('La date de début doit précéder la date de fin.')
        if data.get('date_to') and data['date_to'].year == 9999:
            raise serializers.ValidationError('La date de fin dépasse la plage autorisée.')
        return data


def interaction_history(actor, filters):
    # Fail closed even when there are no objects. These checks grant no object access.
    if not organization_ids(actor,'clients.view') or not organization_ids(actor,'interactions.view'):
        raise PermissionDenied('Les habilitations clients et interactions sont requises.')
    parties=client_queryset(actor,'interactions.view').filter(
        pk__in=client_queryset(actor,'clients.view').values('pk'))
    items=Interaction.objects.filter(party_id__in=parties.values('pk')).select_related('party','author')
    if filters.get('search'):
        text=filters['search']
        items=items.filter(Q(subject__icontains=text)|Q(notes__icontains=text)|Q(party__display_name__icontains=text))
    for key in ['kind','party_id','author_id']:
        if filters.get(key): items=items.filter(**{key:filters[key]})
    zone=ZoneInfo('Africa/Tunis')
    if filters.get('date_from'):
        items=items.filter(occurred_at__gte=datetime.combine(filters['date_from'],time.min,tzinfo=zone))
    if filters.get('date_to'):
        items=items.filter(occurred_at__lt=datetime.combine(filters['date_to']+timedelta(days=1),time.min,tzinfo=zone))
    return items.order_by('-occurred_at','id')


class HistoryItem(serializers.ModelSerializer):
    party_id=serializers.UUIDField(read_only=True)
    author_id=serializers.UUIDField(read_only=True)
    party_name=serializers.CharField(source='party.display_name')
    is_prospect=serializers.SerializerMethodField()
    author_name=serializers.CharField(source='author.username')

    class Meta:
        model=Interaction
        fields=['id','party_id','party_name','is_prospect','kind','subject','notes','occurred_at','author_id','author_name','version']

    def get_is_prospect(self,obj) -> bool:
        return hasattr(obj.party,'prospect')


class HistoryPage(serializers.Serializer):
    count=serializers.IntegerField()
    next=serializers.URLField(allow_null=True)
    previous=serializers.URLField(allow_null=True)
    results=HistoryItem(many=True)


class InteractionHistoryView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']

    @extend_schema(parameters=[HistoryFilters],responses={200:HistoryPage})
    def get(self,request):
        filters=HistoryFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        items=interaction_history(request.user,filters.validated_data).select_related('party__prospect')
        paginator=ClientPagination()
        page=paginator.paginate_queryset(items,request)
        return paginator.get_paginated_response(HistoryItem(page,many=True).data)
