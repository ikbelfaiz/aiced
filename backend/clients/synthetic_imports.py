"""Synthetic source projections; never reconciles by name or edits CRM data."""
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from core.serializers import StrictSerializer
from internal_api.client import request_credentials, ServiceUnavailable
from identity.policies import require
from .models import Party, LegalEntity, PhysicalPerson, CRMProfile, SyntheticImportProjection


@transaction.atomic
def apply_page(organization_id, batch_id, template, source_as_of, published_at, rows):
    if template not in ('physical', 'legal', 'accounts'):
        raise ValidationError('Type synthétique non pris en charge.')
    from iam_consumer.compat import Organization
    Organization.objects.select_for_update().get(pk=organization_id)
    for row in rows:
        cells = row['cells']
        source_id = row['source_id']
        key_column = '5' if template == 'accounts' else '2'
        if not isinstance(source_id, str) or not source_id.strip() or source_id != source_id.strip() or len(source_id) > 160 or cells.get(key_column) != source_id:
            raise ValidationError('Identifiant source synthétique invalide.')
        holder = None
        if template == 'accounts':
            holder_id = cells.get('4')
            if not isinstance(holder_id, str) or not holder_id or holder_id != holder_id.strip():
                raise ValidationError('Identifiant de détenteur synthétique manquant ou invalide.')
            candidates = list(SyntheticImportProjection.objects.filter(organization_id=organization_id, template__in=['physical', 'legal'], source_id=holder_id).select_related('party')[:2])
            if len(candidates) != 1:
                raise ValidationError('Détenteur synthétique introuvable ou ambigu : revue requise.')
            holder = candidates[0].party
        projection = SyntheticImportProjection.objects.select_for_update().filter(organization_id=organization_id, template=template, source_id=source_id).first()
        if projection:
            if holder and projection.party_id != holder.pk:
                raise ValidationError('Changement de détenteur synthétique : revue requise.')
            if projection.row_id == row['row_id']:
                continue
            if (source_as_of, published_at) <= (projection.source_as_of, projection.published_at):
                continue
            projection.batch_id = batch_id
            projection.row_id = row['row_id']
            projection.source_as_of = source_as_of
            projection.published_at = published_at
            projection.cells = cells
            projection.save(update_fields=['batch_id', 'row_id', 'source_as_of', 'published_at', 'cells'])
            continue
        if holder:
            SyntheticImportProjection.objects.create(organization_id=organization_id, party=holder, template=template, source_id=source_id, batch_id=batch_id, row_id=row['row_id'], source_as_of=source_as_of, published_at=published_at, cells=cells)
            continue
        if SyntheticImportProjection.objects.filter(organization_id=organization_id, template__in=['physical', 'legal'], source_id=source_id).exclude(template=template).exists() and SyntheticImportProjection.objects.filter(organization_id=organization_id, template='accounts', cells__contains={'4': source_id}).exists():
            raise ValidationError('Identifiant déjà utilisé par un détenteur de compte : revue requise.')
        def label(value):
            return str(value).strip() if value is not None else ''
        if template == 'legal':
            name = label(cells.get('4'))[:170] or f'Identité source absente {source_id[:120]}'
            display = f'TEST · {name}'[:200]
            party = Party.objects.create(organization_id=organization_id, kind='legal', display_name=display, origin='SYNTHETIC_IMPORT')
            LegalEntity.objects.create(party=party, legal_name=display)
        else:
            first = label(cells.get('4'))[:85] or 'Prénom absent'
            last = label(cells.get('3'))[:85] or f'ID {source_id[:70]}'
            first = f'TEST · {first}'
            party = Party.objects.create(organization_id=organization_id, kind='physical', display_name=f'{first} {last}'[:200], origin='SYNTHETIC_IMPORT')
            PhysicalPerson.objects.create(party=party, first_name=first, last_name=last)
        CRMProfile.objects.create(party=party)
        SyntheticImportProjection.objects.create(organization_id=organization_id, party=party, template=template, source_id=source_id, batch_id=batch_id, row_id=row['row_id'], source_as_of=source_as_of, published_at=published_at, cells=cells)


class SyncInput(StrictSerializer):
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    offset = serializers.IntegerField(min_value=0, max_value=50000, default=0)


class RowInput(StrictSerializer):
    row_id = serializers.UUIDField()
    source_id = serializers.CharField(max_length=160, trim_whitespace=False)
    cells = serializers.DictField()


class PageInput(StrictSerializer):
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    actor_id = serializers.UUIDField()
    template = serializers.ChoiceField(choices=['physical', 'legal'])
    source_as_of = serializers.DateField()
    published_at = serializers.DateTimeField()
    offset = serializers.IntegerField(min_value=0, max_value=50000)
    next_offset = serializers.IntegerField(allow_null=True, min_value=0, max_value=50000)
    rows = RowInput(many=True, max_length=20)


class SyntheticImportSyncView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        inp = SyncInput(data=request.data)
        inp.is_valid(raise_exception=True)
        data = inp.validated_data
        require(request.user, 'clients.view', data['organization_id'], full_scope=True)
        require(request.user, 'clients.view_financial', data['organization_id'], full_scope=True)
        from iam_consumer.compat import Organization
        from django.shortcuts import get_object_or_404
        get_object_or_404(Organization.objects.select_for_update(), pk=data['organization_id'])
        from identity.coordination import admit
        admit(request.user, request)
        require(request.user, 'clients.view', data['organization_id'], full_scope=True)
        require(request.user, 'clients.view_financial', data['organization_id'], full_scope=True)
        from .source_mapping import peer
        result = peer().post('/internal/v1/source-mapping/synthetic-batch', {
            'credentials': request_credentials(request), 'actor_id': str(request.user.pk),
            'organization_id': str(data['organization_id']), 'batch_id': str(data['batch_id']), 'offset': data['offset'],
        })
        page = PageInput(data=result)
        if not page.is_valid():
            raise ServiceUnavailable('Réponse de l’import synthétique incompatible.')
        v = page.validated_data
        if (v['organization_id'] != data['organization_id'] or v['batch_id'] != data['batch_id'] or v['actor_id'] != request.user.pk or v['offset'] != data['offset'] or (v['next_offset'] is not None and (not v['rows'] or v['next_offset'] != data['offset'] + len(v['rows'])))):
            raise ServiceUnavailable('Périmètre de l’import synthétique incompatible.')
        apply_page(v['organization_id'], v['batch_id'], v['template'], v['source_as_of'], v['published_at'], v['rows'])
        from audit.services import record
        record('clients.synthetic_import_synced', actor=request.user, organization_id=v['organization_id'], target_id=v['batch_id'], request=request, context={'offset': v['offset'], 'count': len(v['rows']), 'template': v['template']})
        return Response({'next_offset': v['next_offset'], 'processed': len(v['rows'])})


class SyntheticImportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def get(self, request, party_id):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        from django.db import connection
        from core.admission import AUTH_BARRIER
        from core.client_admission import CLIENT_SCOPE_BARRIER
        from .source_mapping import allowed_party
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '3500ms'")
            for fence in (AUTH_BARRIER, CLIENT_SCOPE_BARRIER):
                cursor.execute('SELECT pg_try_advisory_xact_lock_shared(%s)', [fence])
                if not cursor.fetchone()[0]:
                    raise ServiceUnavailable()
        party = allowed_party(request.user, party_id)
        projection = SyntheticImportProjection.objects.filter(party=party, organization_id=party.organization_id, template__in=['physical', 'legal']).first()
        if not projection:
            return Response({'source': None})
        from .source_mapping import peer
        result = peer().post('/internal/v1/source-mapping/synthetic-read', {'credentials': request_credentials(request), 'actor_id': str(request.user.pk), 'organization_id': str(party.organization_id), 'batch_id': str(projection.batch_id), 'row_id': str(projection.row_id)})
        if result != {'actor_id': str(request.user.pk), 'organization_id': str(party.organization_id), 'batch_id': str(projection.batch_id), 'row_id': str(projection.row_id)}:
            raise ServiceUnavailable()
        if getattr(settings, 'IAM_REMOTE', False):
            from iam_consumer.access import read_principal
            from .reporting import grant_key
            fresh = read_principal(request_credentials(request), persist=False)
            if str(fresh.pk) != str(request.user.pk) or grant_key(fresh) != grant_key(request.user):
                raise PermissionDenied()
            allowed_party(fresh, party_id)
        from ingestion.templates import TEMPLATES
        headers = TEMPLATES[projection.template]['headers']
        accounts = list(SyntheticImportProjection.objects.filter(party=party, organization_id=party.organization_id, template='accounts').order_by('source_id')[:51])
        account_headers = TEMPLATES['accounts']['headers']
        return Response({'source': {'source_id': projection.source_id, 'template': projection.template, 'source_as_of': projection.source_as_of, 'batch_id': str(projection.batch_id), 'fields': [{'label': label or 'Sans libellé', 'value': projection.cells.get(str(i + 1))} for i, label in enumerate(headers) if projection.cells.get(str(i + 1)) not in (None, '')], 'accounts_more': len(accounts) > 50, 'accounts': [{'source_id': account.source_id, 'source_as_of': account.source_as_of, 'fields': [{'label': label or 'Sans libellé', 'value': account.cells.get(str(i + 1))} for i, label in enumerate(account_headers) if account.cells.get(str(i + 1)) not in (None, '')]} for account in accounts[:50]]}})


class SyntheticJobStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        organization_id = serializers.UUIDField().run_validation(request.query_params.get('organization_id'))
        require(request.user, 'clients.view', organization_id, full_scope=True)
        require(request.user, 'clients.view_financial', organization_id, full_scope=True)
        from .source_mapping import peer
        result = peer().post('/internal/v1/source-mapping/synthetic-job-access', {'credentials': request_credentials(request), 'actor_id': str(request.user.pk), 'organization_id': str(organization_id), 'batch_id': str(batch_id)})
        if result != {'actor_id': str(request.user.pk), 'organization_id': str(organization_id), 'batch_id': str(batch_id)}:
            raise ServiceUnavailable()
        from .models import SyntheticImportJob
        job = SyntheticImportJob.objects.filter(batch_id=batch_id, organization_id=organization_id).first()
        return Response({'status': job.status if job else 'pending', 'processed': job.processed if job else 0, 'last_error': job.last_error if job else ''})
