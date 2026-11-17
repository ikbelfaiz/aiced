"""Personal-only planning using existing CRM capabilities; no team scheduling."""
import calendar
from datetime import datetime,date,time,timedelta,timezone as utc_timezone
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Q,Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from core.serializers import StrictSerializer
from iam_consumer.compat import Organization
from identity.policies import organization_ids,require
from identity.coordination import admit
from audit.services import record
from .models import Appointment,Interaction
from .workspace import check_version
from .pagination import ClientPagination


def zone():return ZoneInfo(getattr(settings,'AICED_AGENDA_TIME_ZONE','Africa/Tunis'))
def orgs(actor,write=False):
    result=Organization.objects.all()
    for code in ['clients.view','interactions.view']+(['interactions.manage'] if write else []):
        result=result.filter(pk__in=organization_ids(actor,code))
    return result
def items(actor,write=False):
    allowed=orgs(actor,write)
    if not allowed.exists():raise PermissionDenied()
    return Appointment.objects.filter(owner_id=actor.pk,organization_id__in=allowed.values('pk'))


class AgendaInput(StrictSerializer):
    organization_id=serializers.UUIDField()
    title=serializers.CharField(max_length=160)
    kind=serializers.ChoiceField(choices=Interaction._meta.get_field('kind').choices)
    notes=serializers.CharField(max_length=5000,allow_blank=True,required=False)
    date=serializers.DateField()
    start_time=serializers.RegexField(r'^\d{2}:\d{2}$')
    end_time=serializers.RegexField(r'^\d{2}:\d{2}$')
    version=serializers.IntegerField(min_value=1,required=False)

    def validate(self,data):
        if not 1900<=data['date'].year<=9998:raise serializers.ValidationError('Date hors plage autorisée (1900–9998).')
        def instant(value):
            try:local=datetime.combine(data['date'],time.fromisoformat(value))
            except ValueError:raise serializers.ValidationError('Heure invalide.')
            candidates={local.replace(tzinfo=zone(),fold=fold).astimezone(utc_timezone.utc) for fold in [0,1] if local.replace(tzinfo=zone(),fold=fold).astimezone(utc_timezone.utc).astimezone(zone()).replace(tzinfo=None)==local}
            if len(candidates)!=1:raise serializers.ValidationError('Heure ambiguë ou inexistante dans le fuseau métier.')
            return candidates.pop()
        start,end=instant(data.pop('start_time')),instant(data.pop('end_time'))
        if end<=start:raise serializers.ValidationError('La fin doit suivre le début, le même jour.')
        data.pop('date');data.update(starts_at=start,ends_at=end)
        return data


class AppointmentOutput(serializers.ModelSerializer):
    organization_id=serializers.UUIDField(read_only=True)
    can_edit=serializers.SerializerMethodField()
    def get_can_edit(self,obj)->bool:return orgs(self.context['request'].user,True).filter(pk=obj.organization_id).exists()
    class Meta:
        model=Appointment
        fields=['id','organization_id','title','kind','notes','starts_at','ends_at','version','updated_at','can_edit']


class AgendaFilters(serializers.Serializer):
    month=serializers.RegexField(r'^\d{4}-\d{2}$',required=False)
    day=serializers.DateField(required=False)
    search=serializers.CharField(max_length=200,allow_blank=True,required=False)
    page=serializers.IntegerField(min_value=1,required=False)
    page_size=serializers.IntegerField(min_value=1,max_value=50,required=False)
    def validate(self,data):
        today=timezone.localdate(timezone.now(),zone())
        value=data.get('month',today.strftime('%Y-%m'))
        try:
            year,month=map(int,value.split('-'));first=date(year,month,1)
            if not 1900<=year<=9998:raise ValueError()
        except ValueError:raise serializers.ValidationError('Mois invalide.')
        if data.get('day') and data['day'].strftime('%Y-%m')!=value:raise serializers.ValidationError('Le jour doit appartenir au mois sélectionné.')
        data['month']=value;data['first']=first
        return data


class AgendaPage(serializers.Serializer):
    count=serializers.IntegerField()
    next=serializers.URLField(allow_null=True)
    previous=serializers.URLField(allow_null=True)
    results=AppointmentOutput(many=True)
    days=serializers.DictField(child=serializers.IntegerField())
    month=serializers.CharField()
    business_timezone=serializers.CharField()
    business_date=serializers.DateField()


@transaction.atomic
def save_appointment(request,appointment_id=None):
    actor=request.user
    if appointment_id:
        candidate=get_object_or_404(items(actor,True),pk=appointment_id)
        org=candidate.organization_id
    else:
        # Validate before touching any object or accepting authority fields.
        schema=AgendaInput(data=request.data);schema.is_valid(raise_exception=True)
        org=schema.validated_data['organization_id']
        if not orgs(actor,True).filter(pk=org).exists():raise PermissionDenied()
    Organization.objects.select_for_update().get(pk=org)
    admit(actor,request)
    if not orgs(actor,True).filter(pk=org).exists():raise PermissionDenied()
    if appointment_id:
        item=get_object_or_404(items(actor,True).select_for_update(),pk=appointment_id)
        if 'organization_id' in request.data:raise serializers.ValidationError('Organisation immuable.')
        start=item.starts_at.astimezone(zone());end=item.ends_at.astimezone(zone())
        initial={'organization_id':str(org),'title':item.title,'kind':item.kind,'notes':item.notes,'date':start.date().isoformat(),'start_time':start.strftime('%H:%M'),'end_time':end.strftime('%H:%M')}
        schema=AgendaInput(data={**initial,**request.data});schema.is_valid(raise_exception=True)
        values=dict(schema.validated_data);check_version(item,values);values.pop('organization_id')
        for key,value in values.items():setattr(item,key,value)
        item.version+=1;item.save()
    else:
        values=dict(schema.validated_data)
        if 'version' in values:raise serializers.ValidationError('Version interdite à la création.')
        item=Appointment.objects.create(owner=actor,**values)
    if record('clients.appointments_saved',actor=actor,organization_id=org,target_id=item.pk,request=request) is None:raise RuntimeError('Required appointment audit missing')
    return item


class AgendaView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','post','options']
    @extend_schema(parameters=[AgendaFilters],responses={200:AgendaPage})
    def get(self,request):
        scoped=items(request.user)
        filters=AgendaFilters(data=request.query_params);filters.is_valid(raise_exception=True);values=filters.validated_data
        first=values['first'];last=first+timedelta(days=calendar.monthrange(first.year,first.month)[1])
        scoped=scoped.filter(starts_at__gte=datetime.combine(first,time.min,zone()),starts_at__lt=datetime.combine(last,time.min,zone()))
        if values.get('search'):scoped=scoped.filter(Q(title__icontains=values['search'])|Q(notes__icontains=values['search']))
        days={row['day'].isoformat():row['count'] for row in scoped.order_by().annotate(day=TruncDate('starts_at',tzinfo=zone())).values('day').annotate(count=Count('pk'))}
        if values.get('day'):
            day=values['day'];scoped=scoped.filter(starts_at__gte=datetime.combine(day,time.min,zone()),starts_at__lt=datetime.combine(day+timedelta(days=1),time.min,zone()))
        paginator=ClientPagination();page=paginator.paginate_queryset(scoped.order_by('starts_at','id'),request)
        response=paginator.get_paginated_response(AppointmentOutput(page,many=True,context={'request':request}).data)
        response.data.update(days=days,month=values['month'],business_timezone=str(zone()),business_date=timezone.localdate(timezone.now(),zone()).isoformat())
        return response
    @extend_schema(request=AgendaInput,responses={201:AppointmentOutput})
    def post(self,request):return Response(AppointmentOutput(save_appointment(request),context={'request':request}).data,status=201)


class AppointmentView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','patch','options']
    @extend_schema(responses={200:AppointmentOutput})
    def get(self,request,appointment_id):return Response(AppointmentOutput(get_object_or_404(items(request.user),pk=appointment_id),context={'request':request}).data)
    @extend_schema(request=AgendaInput,responses={200:AppointmentOutput})
    def patch(self,request,appointment_id):return Response(AppointmentOutput(save_appointment(request,appointment_id),context={'request':request}).data)


class AgendaContext(serializers.Serializer):
    organizations=serializers.ListField(child=serializers.DictField())
    business_timezone=serializers.CharField()
    business_date=serializers.DateField()


class AgendaContextView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']
    @extend_schema(responses={200:AgendaContext})
    def get(self,request):
        items(request.user)
        return Response({'organizations':list(orgs(request.user,True).values('id','name')),'business_timezone':str(zone()),'business_date':timezone.localdate(timezone.now(),zone()).isoformat()})
