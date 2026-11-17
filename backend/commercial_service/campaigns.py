"""Private-to-creator manual drafts. No client IDs, targeting execution or sending."""
from uuid import UUID
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import transaction
from django.db.models import Q,F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied,ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core.admission import barrier
from commercial.campaign_contract import CampaignInput,CampaignOutput,CampaignFilters
from commercial_store.models import CampaignDraft,ActorRef
from internal_api.client import ServiceUnavailable
from .access import principal
from .gate import admit
from .journal import record
from .pipeline import PipelinePagination,database_fail_closed
from .views import Conflict


def metadata():
    zone=settings.COMMERCIAL_TIME_ZONE
    return {'business_timezone':zone,'business_date':timezone.now().astimezone(ZoneInfo(zone)).date().isoformat()}


def permissions(data,write=False):
    """IAM decides active membership/grants. These objects reference no Client data.

    Assigned grants permit only one's own preparation; no team ownership or
    customer targeting rule is inferred from either scope.
    """
    try:
        viewed=set();managed=set();names={}
        for org in data['organizations']:
            ident=UUID(org['id'])
            if not isinstance(org['name'],str) or not 0<len(org['name'])<=160:raise ValueError()
            names[ident]=org['name']
        for row in data['grants']:
            org=UUID(row['organization_id']);UUID(row['membership_id'])
            if org not in names or row['scope'] not in ['assigned','organization']:raise ValueError()
            if row['capability']=='opportunities.view':viewed.add(org)
            if row['capability']=='opportunities.manage':managed.add(org)
    except (KeyError,TypeError,ValueError,AttributeError):raise ServiceUnavailable()
    if not viewed:raise PermissionDenied()
    return (viewed & managed if write else viewed),viewed & managed,names


def visible(actor,orgs):
    return CampaignDraft.objects.filter(creator_id=actor.pk,organization_id__in=orgs)


def output(item,managed):
    item.can_edit=item.organization_id in managed
    return CampaignOutput(item).data


class CampaignBase(APIView):
    permission_classes=[IsAuthenticated]
    def actor(self,request,write=False):
        admit();barrier()  # IAM admission through local transaction/required audit
        actor,data=principal(request.user.credentials)
        if actor.pk!=request.user.pk:raise ServiceUnavailable()
        orgs,managed,names=permissions(data,write)
        return actor,orgs,managed,names


class CampaignContextView(CampaignBase):
    http_method_names=['get','options']
    @database_fail_closed
    @transaction.atomic
    def get(self,request):
        actor,orgs,managed,names=self.actor(request)
        return Response({**metadata(),'organizations':[{'id':str(i),'name':names[i]} for i in sorted(managed,key=str)]})


class CampaignsView(CampaignBase):
    http_method_names=['get','post','options']
    @database_fail_closed
    @transaction.atomic
    def get(self,request):
        actor,orgs,managed,_=self.actor(request)
        filters=CampaignFilters(data=request.query_params);filters.is_valid(raise_exception=True)
        values=filters.validated_data;items=visible(actor,orgs)
        if values.get('search'):
            term=values['search'];items=items.filter(Q(name__icontains=term)|Q(description__icontains=term)|Q(targeting_notes__icontains=term))
        ordering=values.get('ordering','-updated_at');field=F(ordering.lstrip('-'))
        items=items.order_by(field.desc(nulls_last=True) if ordering.startswith('-') else field.asc(nulls_last=True),'id')
        paginator=PipelinePagination();page=paginator.paginate_queryset(items,request)
        response=paginator.get_paginated_response([output(item,managed) for item in page])
        response.data.update(metadata())
        self.fresh(request,actor,orgs,managed=managed)
        return response

    def fresh(self,request,actor,orgs,write=False,managed=None):
        current,data=principal(request.user.credentials)
        current_orgs,current_managed,_=permissions(data,write)
        if current.pk!=actor.pk or current_orgs!=orgs or (managed is not None and current_managed!=managed):raise ServiceUnavailable()

    def post(self,request):return self.save(request)

    @database_fail_closed
    @transaction.atomic
    def save(self,request,campaign_id=None):
        actor,orgs,managed,_=self.actor(request,write=True)
        schema=CampaignInput(data=request.data,partial=campaign_id is not None);schema.is_valid(raise_exception=True)
        values=dict(schema.validated_data)
        if campaign_id:
            if 'organization_id' in values:raise ValidationError({'organization_id':'Organisation immuable.'})
            item=get_object_or_404(visible(actor,orgs).select_for_update(),pk=campaign_id)
            if values.pop('version',None)!=item.version:raise Conflict()
        else:
            if 'version' in values:raise ValidationError({'version':'Interdite à la création.'})
            org=values.pop('organization_id',None)
            if org not in orgs:raise PermissionDenied()
            if not values.get('name'):raise ValidationError({'name':'Ce champ est obligatoire.'})
            creator,_=ActorRef.objects.get_or_create(pk=actor.pk,defaults={'username':actor.username})
            item=CampaignDraft(organization_id=org,creator=creator)
        start=values.get('planned_start',item.planned_start);end=values.get('planned_end',item.planned_end)
        if start and end and end<start:raise ValidationError({'planned_end':'La fin doit être postérieure ou égale au début.'})
        for key,value in values.items():setattr(item,key,value)
        if campaign_id:item.version+=1
        self.fresh(request,actor,orgs,write=True)
        item.save()
        if record('commercial.campaign_draft_saved',actor=actor,organization_id=item.organization_id,target_id=item.pk,request=request) is None:
            raise RuntimeError('Required campaign audit missing')
        return Response(output(item,managed),status=200 if campaign_id else 201)


class CampaignDetailView(CampaignsView):
    http_method_names=['get','patch','options']
    @database_fail_closed
    @transaction.atomic
    def get(self,request,campaign_id):
        actor,orgs,managed,_=self.actor(request)
        item=get_object_or_404(visible(actor,orgs),pk=campaign_id)
        self.fresh(request,actor,orgs,managed=managed)
        return Response(output(item,managed))
    def patch(self,request,campaign_id):return self.save(request,campaign_id)
