"""Commercial-owned pipeline; Client owns all object visibility decisions."""
from uuid import UUID
from itertools import islice
from functools import wraps
from time import monotonic
import re
from django.db import transaction, connection, DatabaseError
from django.db.models import Q,F,Case,When,Value,BooleanField
from core.client_admission import CLIENT_SCOPE_BARRIER
from core.admission import AUTH_BARRIER
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from commercial.pipeline_contract import PipelineFilters,PipelineItem
from commercial_store.models import Opportunity
from internal_api.client import ServiceUnavailable
from .access import peer,principal
from .gate import admit
from rest_framework.pagination import PageNumberPagination
from core.request_metrics import record


def scope_parties(actor,ids,deadline=None,scope_state=None,compact=False,search=''):
    result={}
    # Empty calls still validate capabilities, avoiding count-based permission leaks.
    limit=500 if compact else 100
    for start in range(0,max(1,len(ids)),limit):
        chunk=ids[start:start+limit]
        client=peer('client')
        if deadline is not None:client.timeout=min(3,remaining(deadline))
        payload={'credentials':actor.credentials,'party_ids':chunk}
        if compact:payload['search']=search
        data=client.post('/internal/v1/clients/opportunity-scope'+('-batch' if compact else ''),payload)
        if deadline is not None:remaining(deadline)
        try:
            if UUID(data['actor_id'])!=actor.pk or not isinstance(data['parties'],list) or len(data['parties'])>len(chunk):raise ValueError()
            if scope_state is not None:
                revision=data['scope_revision']
                if not isinstance(revision,str) or not re.fullmatch('[a-f0-9]{64}',revision):raise ValueError()
                if scope_state and revision!=scope_state[0]:raise ValueError()
                if not scope_state:scope_state.append(revision)
            for row in data['parties']:
                ident=str(UUID(row['id']))
                if ident not in chunk or ident in result:raise ValueError()
                if compact:
                    if type(row['name_match']) is not bool:raise ValueError()
                elif not isinstance(row['display_name'],str) or not 0<len(row['display_name'])<=200 or type(row['can_edit']) is not bool:raise ValueError()
                result[ident]=row
        except (KeyError,TypeError,ValueError):raise ServiceUnavailable()
    return result


# Below the existing 5s revocation lock wait, gateway and database limits.
# A timeout returns no partial rows or counts; no persistent authorization cache.
PIPELINE_BUDGET_SECONDS=4
BATCH_SIZE=500


def remaining(deadline):
    seconds=deadline-monotonic()
    if seconds<=0:
        record('pipeline_budget_exhausted', remaining_seconds=round(seconds,6))
        raise ServiceUnavailable('Budget de lecture du pipeline dépassé.')
    return seconds


def database_fail_closed(method):
    @wraps(method)
    def wrapped(*args,**kwargs):
        try:return method(*args,**kwargs)
        except DatabaseError as error:
            record('pipeline_failure', phase='database')
            raise ServiceUnavailable() from error
    return wrapped


def scan(actor,items,values,deadline,scope_state=None,set_sql_budget=None):
    """Server cursor + one authorized batch + one public page, independent of offset.

    Client decides every object. No optimization based on organization identifiers
    or a previous request's decisions is permitted here.
    """
    size=values.get('page_size',8)
    start=(values.get('page',1)-1)*size
    counts={status:0 for status in ['open','won','lost']}
    count=0;rows=[]
    term=values.get('search','').casefold()
    iterator=iter(items.iterator(chunk_size=BATCH_SIZE))
    batches=0
    try:
        while True:
            remaining(deadline)
            if set_sql_budget is not None:set_sql_budget(remaining(deadline))
            batch=list(islice(iterator,BATCH_SIZE))
            if not batch:break
            batches+=1
            ids=list(dict.fromkeys(str(item.party_id) for item in batch))
            visible=scope_parties(actor,ids,deadline,scope_state,compact=True,search=values.get('search',''))
            for item in batch:
                party=visible.get(str(item.party_id))
                if party is None:continue
                if term and not item.pipeline_text_match and not party['name_match']:continue
                counts[item.status]+=1
                if values.get('status') and item.status!=values['status']:continue
                if start<=count<start+size:
                    rows.append(item)
                count+=1
    finally:
        iterator.close()
        record('pipeline_scan', batches=batches, remaining_seconds=round(deadline-monotonic(),6))
    return count,counts,rows


class PipelinePagination(PageNumberPagination):
    page_size=8
    page_size_query_param='page_size'
    max_page_size=50


class PipelineView(APIView):
    permission_classes=[IsAuthenticated]
    http_method_names=['get','options']

    @database_fail_closed
    @transaction.atomic
    def get(self,request):
        deadline=monotonic()+PIPELINE_BUDGET_SECONDS
        # One opportunity snapshot per request; live Client/IAM decisions are
        # protected by the existing shared admission barriers, not SQL joins.
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute("SELECT set_config('statement_timeout', %s, true)",[f'{PIPELINE_BUDGET_SECONDS*1000}ms'])
            cursor.execute("SET LOCAL work_mem = '4MB'")
        admit()
        # Fail immediately behind a mutation: never extend a revocation wait
        # while waiting to acquire the second shared barrier.
        with connection.cursor() as cursor:
            for key in [AUTH_BARRIER,CLIENT_SCOPE_BARRIER]:
                remaining(deadline)
                cursor.execute('SELECT pg_try_advisory_xact_lock_shared(%s)',[key])
                if not cursor.fetchone()[0]:
                    record('pipeline_failure', phase='iam_barrier' if key==AUTH_BARRIER else 'client_barrier')
                    raise ServiceUnavailable()
        filters=PipelineFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values=filters.validated_data
        scope_state=[]
        scope_parties(request.user,[],deadline,scope_state)  # required even for an empty database
        items=Opportunity.objects.all()
        if values.get('search'):
            term=values['search']
            # Keep PostgreSQL icontains for title/notes and Python casefold for
            # Client names, exactly as the existing public contract.
            items=items.annotate(pipeline_text_match=Case(When(Q(title__icontains=term)|Q(notes__icontains=term),then=Value(True)),default=Value(False),output_field=BooleanField()))
        ordering=values.get('ordering','-updated_at')
        field=F(ordering.lstrip('-'))
        items=items.order_by(field.desc(nulls_last=True) if ordering.startswith('-') else field.asc(nulls_last=True),'id')
        def set_sql_budget(seconds):
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('statement_timeout', %s, true)",[f'{max(1,int(seconds*1000))}ms'])
        count,counts,rows=scan(request.user,items,values,deadline,scope_state,set_sql_budget)
        # range is O(1), including arbitrarily deep offsets. DRF keeps existing
        # invalid-page handling and next/previous URL construction.
        paginator=PipelinePagination();paginator.paginate_queryset(range(count),request)
        visible=scope_parties(request.user,list(dict.fromkeys(str(item.party_id) for item in rows)),deadline,scope_state)
        for item in rows:
            party=visible.get(str(item.party_id))
            if party is None:raise ServiceUnavailable()
            item.party_name=party['display_name'];item.can_edit=party['can_edit']
        # Fresh IAM check before exposing the response; no decision is cached.
        actor,_=principal(request.user.credentials,timeout=min(3,remaining(deadline)))
        scope_parties(request.user,[],deadline,scope_state)
        remaining(deadline)
        if actor.pk!=request.user.pk:raise ServiceUnavailable()
        response=paginator.get_paginated_response(PipelineItem(rows,many=True).data)
        response.data['statuses']=counts
        return response
