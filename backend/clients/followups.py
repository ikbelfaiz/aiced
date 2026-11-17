"""Read-only prospect worklist. Calendar dates belong to Africa/Tunis."""
from zoneinfo import ZoneInfo
from django.utils import timezone
from django.db.models import Q, F
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from identity.policies import organization_ids
from .models import Prospect
from .prospects import prospect_queryset, ProspectOutput
from .pagination import ClientPagination


class FollowupFilters(serializers.Serializer):
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Prospect.Status.values, required=False, allow_blank=True)
    bucket = serializers.ChoiceField(choices=['overdue','today','upcoming','unscheduled'], required=False, allow_blank=True)
    ordering = serializers.ChoiceField(choices=['next_action_date','-next_action_date','display_name','-display_name'], required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False)

    def validate(self, data):
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise serializers.ValidationError('La date de début doit précéder la date de fin.')
        return data


class FollowupPage(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ProspectOutput(many=True)
    business_date = serializers.DateField()
    business_timezone = serializers.CharField()
    buckets = serializers.DictField(child=serializers.IntegerField())


class ProspectFollowupsView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get','options']

    @extend_schema(parameters=[FollowupFilters], responses={200:FollowupPage})
    def get(self, request):
        if not organization_ids(request.user,'clients.view') or not organization_ids(request.user,'prospects.view'):
            raise PermissionDenied()
        filters = FollowupFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        items = prospect_queryset(request.user)
        if values.get('search'):
            term = values['search']
            items = items.filter(Q(party__display_name__icontains=term)|Q(source__icontains=term)|Q(next_action__icontains=term))
        if values.get('status'): items = items.filter(status=values['status'])
        if values.get('date_from'): items = items.filter(next_action_date__gte=values['date_from'])
        if values.get('date_to'): items = items.filter(next_action_date__lte=values['date_to'])
        today = timezone.localdate(timezone.now(), ZoneInfo('Africa/Tunis'))
        buckets = {'overdue':Q(next_action_date__lt=today), 'today':Q(next_action_date=today),
                   'upcoming':Q(next_action_date__gt=today), 'unscheduled':Q(next_action_date__isnull=True)}
        # Counts respect every other filter and object scope, before bucket selection.
        counts = {key:items.filter(condition).count() for key,condition in buckets.items()}
        if values.get('bucket'): items = items.filter(buckets[values['bucket']])
        ordering = values.get('ordering','next_action_date')
        field = 'party__display_name' if 'display_name' in ordering else 'next_action_date'
        expression = F(field).desc(nulls_last=True) if ordering.startswith('-') else F(field).asc(nulls_last=True)
        items = items.order_by(expression,'party_id')
        paginator = ClientPagination()
        page = paginator.paginate_queryset(items,request)
        response = paginator.get_paginated_response(ProspectOutput(page,many=True,context={'request':request}).data)
        response.data.update(business_date=today.isoformat(),business_timezone='Africa/Tunis',buckets=counts)
        return response
