from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from core.serializers import StrictSerializer
from internal_api.base import PrivateView
from internal_api.contracts import Credentials
from internal_api.views import resolve
from identity.policies import grants
from .policies import client_queryset
import hashlib
import json


def scope_revision(actor):
    """Opaque request-coherence marker, never an authorization credential.

    Admission fences serialize mutations; this also detects time-based grant
    expiry between batches. Every RPC still resolves the live IAM session.
    """
    if hasattr(actor,'_iam_grants'):
        rows=[(str(r['membership_id']),str(r['organization_id']),r['scope'],r['capability']) for r in actor._iam_grants]
    else:
        rows=[tuple(map(str,r)) for r in grants(actor).values_list('membership_id','membership__organization_id','scope','role__permissions__code')]
    return hashlib.sha256(json.dumps(sorted(rows),separators=(',',':')).encode()).hexdigest()


class PipelineScopeInput(StrictSerializer):
    credentials=Credentials()
    party_ids=serializers.ListField(child=serializers.UUIDField(),max_length=100,allow_empty=True)


class CompactScopeInput(PipelineScopeInput):
    party_ids=serializers.ListField(child=serializers.UUIDField(),max_length=500,allow_empty=True)
    search=serializers.CharField(max_length=200,allow_blank=True,default='')


@extend_schema(exclude=True)
class OpportunityScopeView(PrivateView):
    audience='client'
    compact=False

    def post(self,request):
        if self.service!='commercial':raise PermissionDenied()
        data=self.validated(CompactScopeInput if self.compact else PipelineScopeInput,request)
        actor=resolve(data['credentials'])
        if not grants(actor,'clients.view').exists() or not grants(actor,'opportunities.view').exists():
            raise PermissionDenied()
        ids=data['party_ids']
        visible=client_queryset(actor,'opportunities.view').filter(pk__in=client_queryset(actor,'clients.view').values('pk'))
        parties=visible.filter(pk__in=ids).order_by('pk')
        if self.compact:
            term=data['search'].casefold()
            rows=[{'id':str(p.pk),'name_match':bool(term and term in p.display_name.casefold())} for p in parties.only('id','display_name')]
            return Response({'actor_id':str(actor.pk),'scope_revision':scope_revision(actor),'parties':rows})
        editable=set(client_queryset(actor,'opportunities.manage').filter(pk__in=parties.values('pk')).values_list('pk',flat=True))
        return Response({'actor_id':str(actor.pk),'scope_revision':scope_revision(actor),'parties':[{'id':str(p.pk),'display_name':p.display_name,'can_edit':p.pk in editable} for p in parties]})


@extend_schema(exclude=True)
class CompactOpportunityScopeView(OpportunityScopeView):
    # 500 UUID + boolean rows fit below the existing 64KiB HTTP envelope,
    # including the worst-case UUID spelling. No names or authority are cached.
    compact=True
