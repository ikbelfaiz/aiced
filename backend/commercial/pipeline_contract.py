"""Additive public schema, with no imported persistence models or local fallback."""
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from internal_api.client import ServiceUnavailable


class PipelineFilters(serializers.Serializer):
    search=serializers.CharField(max_length=200,required=False,allow_blank=True)
    status=serializers.ChoiceField(choices=['open','won','lost'],required=False,allow_blank=True)
    ordering=serializers.ChoiceField(choices=['-updated_at','updated_at','title','-title','due_date','-due_date'],required=False)
    page=serializers.IntegerField(min_value=1,required=False)
    page_size=serializers.IntegerField(min_value=1,max_value=50,required=False)


class PipelineItem(serializers.Serializer):
    id=serializers.UUIDField()
    party_id=serializers.UUIDField()
    party_name=serializers.CharField()
    title=serializers.CharField()
    notes=serializers.CharField(allow_blank=True)
    amount=serializers.DecimalField(max_digits=18,decimal_places=3,allow_null=True)
    currency=serializers.CharField()
    status=serializers.CharField()
    due_date=serializers.DateField(allow_null=True)
    version=serializers.IntegerField()
    updated_at=serializers.DateTimeField()
    can_edit=serializers.BooleanField()


class PipelinePage(serializers.Serializer):
    count=serializers.IntegerField()
    next=serializers.URLField(allow_null=True)
    previous=serializers.URLField(allow_null=True)
    results=PipelineItem(many=True)
    statuses=serializers.DictField(child=serializers.IntegerField())


class PipelineContractView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']

    @extend_schema(parameters=[PipelineFilters],responses={200:PipelinePage})
    def get(self,request):
        raise ServiceUnavailable('La route pipeline doit être servie par Commercial.')
