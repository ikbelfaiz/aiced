"""Bounded descriptive CRM reads. No finance, attribution or inferred outcome."""
import json
from datetime import datetime,time,timedelta
from time import monotonic
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import connection,transaction,DatabaseError
from django.db.models import Count,Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from core.admission import AUTH_BARRIER
from core.client_admission import CLIENT_SCOPE_BARRIER
from internal_api.client import ServiceUnavailable
from identity.policies import organization_ids
from .history import interaction_history
from .agenda import items as appointments
from .prospects import prospect_queryset

KINDS=['call','email','meeting','visit']

def zone():return ZoneInfo(settings.AICED_REPORT_TIME_ZONE)

class ActivityReportFilters(serializers.Serializer):
    date_from=serializers.DateField(required=False)
    date_to=serializers.DateField(required=False)
    kind=serializers.ChoiceField(choices=KINDS,required=False)

    def validate(self,data):
        today=timezone.localdate(timezone.now(),zone())
        end=data.get('date_to',today);start=data.get('date_from',end-timedelta(days=29))
        if not 1900<=start.year<=9998 or not 1900<=end.year<=9998 or start>end or (end-start).days>=93:
            raise serializers.ValidationError('Période de 1 à 93 jours, entre 1900 et 9998, début avant fin.')
        return {**data,'date_from':start,'date_to':end}

class ActivityReport(serializers.Serializer):
    date_from=serializers.DateField()
    date_to=serializers.DateField()
    business_date=serializers.DateField()
    business_timezone=serializers.CharField()
    generated_at=serializers.DateTimeField()
    kind=serializers.CharField(allow_null=True)
    interactions=serializers.DictField(allow_null=True)
    appointments=serializers.DictField(allow_null=True)
    followups=serializers.DictField(allow_null=True)

def permission(actor,code):return bool(organization_ids(actor,'clients.view')) and bool(organization_ids(actor,code))

def grant_key(actor):return sorted(json.dumps(row,sort_keys=True) for row in actor._iam_grants)

def calculate(actor,values,budget,require_activity=True,metric_permission=permission):
    start,end=values['date_from'],values['date_to'];tz=zone()
    lower=datetime.combine(start,time.min,tzinfo=tz)
    upper=datetime.combine(end+timedelta(days=1),time.min,tzinfo=tz)
    result={'date_from':start,'date_to':end,'business_timezone':str(tz),
            'business_date':timezone.localdate(timezone.now(),tz),'generated_at':timezone.now(),
            'kind':values.get('kind'),'interactions':None,'appointments':None,'followups':None}
    def aggregate(query,column):
        query=query.filter(**{column+'__gte':lower,column+'__lt':upper})
        if values.get('kind'):query=query.filter(kind=values['kind'])
        budget()
        by_kind={k:0 for k in KINDS}
        days={}
        # READ COMMITTED: the metric snapshot MUST follow the visibility fence.
        # One SQL grouping yields both series and totals without a second scan.
        for row in query.order_by().annotate(day=TruncDate(column,tzinfo=tz)).values('day','kind').annotate(count=Count('pk')):
            if row['kind'] not in by_kind:raise ServiceUnavailable('Type d’activité invalide.')
            by_kind[row['kind']]+=row['count']
            day=row['day'].isoformat();days[day]=days.get(day,0)+row['count']
        daily=[{'date':(start+timedelta(days=i)).isoformat(),'count':days.get((start+timedelta(days=i)).isoformat(),0)} for i in range((end-start).days+1)]
        budget()
        if sum(by_kind.values())!=sum(r['count'] for r in daily):raise ServiceUnavailable()
        return {'total':sum(by_kind.values()),'by_kind':by_kind,'daily':daily}
    if metric_permission(actor,'interactions.view'):
        # Reuse the existing object policy, but apply this report's explicit zone.
        result['interactions']=aggregate(interaction_history(actor,{}),'occurred_at')
        result['appointments']=aggregate(appointments(actor),'starts_at')
    if metric_permission(actor,'prospects.view'):
        today=result['business_date'];budget()
        result['followups']=prospect_queryset(actor).aggregate(
            overdue=Count('pk',filter=Q(next_action_date__lt=today)),
            today=Count('pk',filter=Q(next_action_date=today)),
            upcoming=Count('pk',filter=Q(next_action_date__gt=today)),
            unscheduled=Count('pk',filter=Q(next_action_date__isnull=True)))
    if require_activity and all(result[key] is None for key in ['interactions','appointments','followups']):raise PermissionDenied()
    budget()
    return result

class CommercialActivityView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']
    calculation=staticmethod(calculate)

    @extend_schema(parameters=[ActivityReportFilters],responses={200:ActivityReport})
    def get(self,request):
        filters=ActivityReportFilters(data=request.query_params);filters.is_valid(raise_exception=True)
        deadline=monotonic()+4
        def remaining():
            value=deadline-monotonic()
            if value<=0:raise ServiceUnavailable('Budget du rapport dépassé.')
            return value
        def budget():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('statement_timeout',%s,true)",[f'{max(1,int(remaining()*1000))}ms'])
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                    cursor.execute("SET LOCAL work_mem = '4MB'")
                    for key in [AUTH_BARRIER,CLIENT_SCOPE_BARRIER]:
                        cursor.execute('SELECT pg_try_advisory_xact_lock_shared(%s)',[key])
                        if not cursor.fetchone()[0]:raise ServiceUnavailable()
                budget()
                actor=request.user
                if getattr(settings,'IAM_REMOTE',False):
                    from iam_consumer.access import read_principal
                    actor=read_principal(actor.credentials,persist=False,timeout=min(3,remaining()))
                    if str(actor.pk)!=str(request.user.pk):raise PermissionDenied()
                result=self.calculation(actor,filters.validated_data,budget)
                if getattr(settings,'IAM_REMOTE',False):
                    fresh=read_principal(actor.credentials,persist=False,timeout=min(3,remaining()))
                    if str(fresh.pk)!=str(actor.pk) or grant_key(fresh)!=grant_key(actor):raise ServiceUnavailable()
                remaining()
                return Response(result)
        except DatabaseError as exc:raise ServiceUnavailable() from exc
