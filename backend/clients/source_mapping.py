"""Client-authorized synthetic preparation; no real source/identity linkage."""
from time import monotonic
import re
from django.conf import settings
from django.db import connection, transaction, DatabaseError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from core.admission import AUTH_BARRIER
from core.client_admission import CLIENT_SCOPE_BARRIER
from identity.policies import grants, organization_ids
from internal_api.client import InternalClient, ServiceUnavailable, request_credentials
from .policies import client_queryset

SCENARIOS = ('unique', 'ambiguous', 'missing', 'duplicate', 'multiple_accounts', 'conflicting_identifiers')


def allowed_party(actor, party_id):
    # Client IAM snapshots intentionally omit imports.*; Integration alone checks
    # that grant using its existing IAM audience. Never broaden the snapshot.
    for code in ['clients.view', 'clients.view_financial']:
        if not grants(actor, code).exists():
            raise PermissionDenied('Habilitations client, financières et revue des imports requises pour la démonstration.')
    visible = client_queryset(actor, 'clients.view').filter(prospect__isnull=True)
    financial = client_queryset(actor, 'clients.view_financial').filter(pk__in=visible.values('pk'))
    return get_object_or_404(financial.filter(
        organization_id__in=organization_ids(actor, 'clients.view_financial', full_scope=True), pk=party_id))


def validate_examples(data):
    """Reject accidental real-source/extra fields even from the trusted peer."""
    def ref(value):
        return isinstance(value, str) and bool(re.fullmatch(r'SYNTH-[A-Za-z0-9-]{1,100}', value))
    try:
        if data['dataset_version'] != 'SYNTH-MAPPING-v1':
            raise ValueError()
        records = data['records']; relations = data['relationships']
        if not isinstance(records, list) or not isinstance(relations, list) or not 1 <= len(records) <= 10 or not 1 <= len(relations) <= 10:
            raise ValueError()
        for row in records:
            if set(row) - {'ref','template','source_id','alternate_id','fixture_client','account_id','holder_D','identifier_AH','validation_status','provenance'}:
                raise ValueError()
            if not ref(row['ref']) or row['template'] not in ('physical','legal','accounts') or row['validation_status'] not in ('synthetic_mapping_blocked','synthetic_technical_only'):
                raise ValueError()
            for key in ['source_id','alternate_id','fixture_client','account_id','holder_D','identifier_AH']:
                if row.get(key) is not None and not ref(row[key]):
                    raise ValueError()
            provenance = row['provenance']
            if set(provenance) != {'dataset','batch_reference','row_number','source_as_of','digest','publication_state'} or provenance['dataset'] != data['dataset_version'] or not ref(provenance['batch_reference']) or provenance['publication_state'] != 'illustrative_fixture_not_a_published_import' or provenance['source_as_of'] != '2024-06-01' or type(provenance['row_number']) is not int or not 2 <= provenance['row_number'] <= 20 or not re.fullmatch('[a-f0-9]{64}',provenance['digest']):
                raise ValueError()
        record_refs = {row['ref'] for row in records}
        for row in relations:
            if set(row) != {'account_ref','status','person_candidates','fixture_client_candidates','confirmed'} or row['confirmed'] is not False or row['status'] not in ('candidate_unique','missing_identifier','conflicting_identifiers','duplicate_identifier','ambiguous_candidate') or row['account_ref'] not in record_refs:
                raise ValueError()
            for key in ['person_candidates','fixture_client_candidates']:
                if not isinstance(row[key], list) or len(row[key]) > 10 or any(not ref(value) for value in row[key]):
                    raise ValueError()
            if not set(row['person_candidates']) <= record_refs:
                raise ValueError()
        # Explicit allowlist: arbitrary extra top-level content never escapes.
        return {key:data[key] for key in ['mode','scenario','dataset_version','real_source_access','mapping_approved','relationships_persisted','records','relationships','context_party_id']}
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ServiceUnavailable('Réponse synthétique incompatible, aucune donnée affichée.') from exc


def peer():
    # Reuse existing signed transport, DNS and credentials; no new ingress/key.
    key_id = settings.INTEGRATION_AUDIT_KEY_ID
    key = settings.AICED_INTERNAL_KEYS.get(key_id)
    if not settings.INTEGRATION_AUDIT_URL or not key or key['service'] != 'client_crm':
        raise ServiceUnavailable('Transport source non configuré.')
    return InternalClient(settings.INTEGRATION_AUDIT_URL, key_id, key['secret'], 'integration')


class SourceMappingPreviewView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'options']

    @extend_schema(parameters=[OpenApiParameter('scenario', str, enum=list(SCENARIOS))], responses={200: dict})
    def get(self, request, party_id):
        if set(request.query_params) - {'scenario'} or any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            raise ValidationError('Paramètres de démonstration invalides.')
        scenario = request.query_params.get('scenario', 'unique')
        if scenario not in SCENARIOS:
            raise ValidationError('Scénario synthétique inconnu.')
        deadline = monotonic() + 4
        def remaining():
            left = deadline - monotonic()
            if left <= 0:
                raise ServiceUnavailable('Budget de prévisualisation dépassé.')
            return min(3, left)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                    cursor.execute("SET LOCAL statement_timeout = '3500ms'")
                    for fence in [AUTH_BARRIER, CLIENT_SCOPE_BARRIER]:
                        cursor.execute('SELECT pg_try_advisory_xact_lock_shared(%s)', [fence])
                        if not cursor.fetchone()[0]:
                            raise ServiceUnavailable()
                actor = request.user
                if getattr(settings, 'IAM_REMOTE', False):
                    from iam_consumer.access import read_principal
                    actor = read_principal(request_credentials(request), persist=False, timeout=remaining())
                    if str(actor.pk) != str(request.user.pk):
                        raise PermissionDenied()
                party = allowed_party(actor, party_id)
                remote = peer()
                remote.timeout = remaining()
                data = remote.post('/internal/v1/source-mapping/preview', {
                    'credentials': request_credentials(request), 'actor_id': str(actor.pk),
                    'organization_id': str(party.organization_id), 'party_id': str(party.pk),
                    'mode': 'synthetic', 'scenario': scenario})
                if (data.get('mode') != 'synthetic' or data.get('real_source_access') is not False or
                    data.get('mapping_approved') is not False or data.get('relationships_persisted') is not False or
                    data.get('scenario') != scenario or data.get('actor_id') != str(actor.pk) or
                    data.get('organization_id') != str(party.organization_id) or data.get('context_party_id') != str(party.pk)):
                    raise ServiceUnavailable('Réponse source incompatible.')
                if getattr(settings, 'IAM_REMOTE', False):
                    from .reporting import grant_key
                    fresh = read_principal(request_credentials(request), persist=False, timeout=remaining())
                    if str(fresh.pk) != str(actor.pk) or grant_key(fresh) != grant_key(actor):
                        raise PermissionDenied()
                    allowed_party(fresh, party_id)
                remaining()
                return Response(validate_examples(data))
        except DatabaseError as exc:
            raise ServiceUnavailable() from exc
