"""Additive campaign schema only: never a Client/monolith persistence fallback."""
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from core.serializers import StrictSerializer
from internal_api.client import ServiceUnavailable


class CampaignInput(StrictSerializer):
    organization_id=serializers.UUIDField(help_text='Organisation à la création uniquement ; immuable ensuite.')
    name=serializers.CharField(max_length=160)
    description=serializers.CharField(max_length=5000,allow_blank=True,required=False)
    targeting_notes=serializers.CharField(max_length=2000,allow_blank=True,required=False)
    planned_start=serializers.DateField(allow_null=True,required=False)
    planned_end=serializers.DateField(allow_null=True,required=False)
    version=serializers.IntegerField(min_value=1,required=False)


class CampaignOutput(serializers.Serializer):
    id=serializers.UUIDField()
    organization_id=serializers.UUIDField()
    creator_id=serializers.UUIDField()
    name=serializers.CharField()
    description=serializers.CharField(allow_blank=True)
    targeting_notes=serializers.CharField(allow_blank=True)
    planned_start=serializers.DateField(allow_null=True)
    planned_end=serializers.DateField(allow_null=True)
    status=serializers.CharField(help_text='Toujours draft ; aucune activation disponible.')
    version=serializers.IntegerField()
    created_at=serializers.DateTimeField()
    updated_at=serializers.DateTimeField()
    can_edit=serializers.BooleanField()


class CampaignFilters(serializers.Serializer):
    search=serializers.CharField(max_length=200,allow_blank=True,required=False)
    ordering=serializers.ChoiceField(choices=['-updated_at','updated_at','name','-name','planned_start','-planned_start'],required=False)
    page=serializers.IntegerField(min_value=1,required=False)
    page_size=serializers.IntegerField(min_value=1,max_value=50,required=False)


class CampaignPage(serializers.Serializer):
    count=serializers.IntegerField()
    next=serializers.URLField(allow_null=True)
    previous=serializers.URLField(allow_null=True)
    results=CampaignOutput(many=True)
    business_timezone=serializers.CharField()
    business_date=serializers.DateField()


class CampaignOrganization(serializers.Serializer):
    id=serializers.UUIDField()
    name=serializers.CharField()


class CampaignContext(serializers.Serializer):
    organizations=CampaignOrganization(many=True)
    business_timezone=serializers.CharField()
    business_date=serializers.DateField()


class CampaignContractView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','post','options']
    @extend_schema(parameters=[CampaignFilters],responses={200:CampaignPage})
    def get(self,request):raise ServiceUnavailable('Le service Commercial est requis.')
    @extend_schema(request=CampaignInput,responses={201:CampaignOutput})
    def post(self,request):raise ServiceUnavailable('Le service Commercial est requis.')


class CampaignDetailContractView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','patch','options']
    @extend_schema(responses={200:CampaignOutput})
    def get(self,request,campaign_id):raise ServiceUnavailable('Le service Commercial est requis.')
    @extend_schema(request=CampaignInput,responses={200:CampaignOutput})
    def patch(self,request,campaign_id):raise ServiceUnavailable('Le service Commercial est requis.')


class CampaignContextContractView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']
    @extend_schema(responses={200:CampaignContext})
    def get(self,request):raise ServiceUnavailable('Le service Commercial est requis.')
