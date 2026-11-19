"""Signed synthetic preview; real source reads are explicitly disabled."""
from .mapping_examples import preview, SCENARIOS


from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from core.serializers import StrictSerializer
from internal_api.base import PrivateView
from internal_api.contracts import Credentials
from integration_store.models import ActorRef
from .access import RemoteAccess


class MappingInput(StrictSerializer):
    credentials = Credentials()
    actor_id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    party_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=['synthetic', 'published'])
    scenario = serializers.ChoiceField(choices=SCENARIOS)


@extend_schema(exclude=True)
class MappingPreview(PrivateView):
    audience = 'integration'

    def post(self, request):
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(MappingInput, request)
        # No configuration switch or caller assertion can approve real visibility.
        if data['mode'] != 'synthetic':
            raise PermissionDenied('Mapping et visibilité source par objet non approuvés par AMEN INVEST.')
        actor = ActorRef(pk=data['actor_id'])
        actor.credentials = data['credentials']
        RemoteAccess().authorize(actor, data['organization_id'])
        return Response({**preview(data['scenario']), 'actor_id': str(actor.pk),
                         'organization_id': str(data['organization_id']), 'context_party_id': str(data['party_id'])})


class SyntheticBatchInput(StrictSerializer):
    credentials = Credentials()
    actor_id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    offset = serializers.IntegerField(min_value=0, max_value=50000)


class SyntheticBatchPage(PrivateView):
    audience = 'integration'

    def post(self, request):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(SyntheticBatchInput, request)
        actor = ActorRef(pk=data['actor_id'])
        actor.credentials = data['credentials']
        RemoteAccess().authorize(actor, data['organization_id'], 'imports.approve')
        from django.shortcuts import get_object_or_404
        from integration_store.models import ImportBatch, SourceSnapshot
        batch = get_object_or_404(ImportBatch, pk=data['batch_id'], organization_id=data['organization_id'], data_scope='synthetic', status='published', template__in=['physical', 'legal'])
        response = synthetic_page(batch, data['offset'])
        return Response({**response, 'actor_id': str(actor.pk)})


def synthetic_page(batch, offset):
        from integration_store.models import SourceSnapshot
        snapshots = list(SourceSnapshot.objects.filter(row__batch=batch).select_related('row').order_by('row__number')[offset:offset + 21])
        import json
        rows = []
        for snapshot in snapshots[:20]:
            row = {'row_id': str(snapshot.row_id), 'source_id': snapshot.external_key, 'cells': snapshot.row.cells}
            if len(json.dumps([*rows, row]).encode('utf-8')) > 48000:
                if not rows:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError('Ligne synthétique trop volumineuse pour la synchronisation.')
                break
            rows.append(row)
        more = len(snapshots) > len(rows)
        return {'organization_id': str(batch.organization_id), 'batch_id': str(batch.pk), 'template': batch.template, 'source_as_of': batch.source_as_of, 'published_at': batch.published_at, 'offset': offset, 'next_offset': offset + len(rows) if more else None, 'rows': rows}


class WorkerInput(StrictSerializer):
    batch_id = serializers.UUIDField()
    offset = serializers.IntegerField(min_value=0, max_value=50000)


class SyntheticWorkerPage(PrivateView):
    audience = 'integration'

    def post(self, request):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(WorkerInput, request)
        from django.shortcuts import get_object_or_404
        from integration_store.models import ImportBatch
        batch = get_object_or_404(ImportBatch, pk=data['batch_id'], data_scope='synthetic', status='published', template__in=['physical', 'legal', 'accounts'])
        return Response(synthetic_page(batch, data['offset']))


class DiscoveryInput(StrictSerializer):
    offset = serializers.IntegerField(min_value=0, max_value=100000, default=0)


class SyntheticWorkerDiscovery(PrivateView):
    audience = 'integration'

    def post(self, request):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(DiscoveryInput, request)
        from integration_store.models import ImportBatch
        batches = list(ImportBatch.objects.filter(data_scope='synthetic', status='published', template__in=['physical', 'legal', 'accounts']).order_by('published_at', 'id')[data['offset']:data['offset']+101])
        return Response({'batches': [{'batch_id': str(b.pk), 'organization_id': str(b.organization_id), 'template': b.template} for b in batches[:100]], 'next_offset': data['offset']+100 if len(batches)>100 else None})


class SyntheticReadInput(StrictSerializer):
    credentials = Credentials()
    actor_id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    row_id = serializers.UUIDField()


class SyntheticJobAccessInput(StrictSerializer):
    credentials = Credentials()
    actor_id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()


class SyntheticJobAccess(PrivateView):
    audience = 'integration'

    def post(self, request):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(SyntheticJobAccessInput, request)
        actor = ActorRef(pk=data['actor_id'])
        actor.credentials = data['credentials']
        RemoteAccess().authorize(actor, data['organization_id'])
        from django.shortcuts import get_object_or_404
        from integration_store.models import ImportBatch
        batch = get_object_or_404(ImportBatch, pk=data['batch_id'], organization_id=data['organization_id'], data_scope='synthetic', status='published', template__in=['physical', 'legal', 'accounts'])
        return Response({'actor_id': str(actor.pk), 'organization_id': str(batch.organization_id), 'batch_id': str(batch.pk)})


class SyntheticRead(PrivateView):
    audience = 'integration'

    def post(self, request):
        from core.synthetic_guard import require_synthetic_database
        require_synthetic_database()
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(SyntheticReadInput, request)
        actor = ActorRef(pk=data['actor_id'])
        actor.credentials = data['credentials']
        RemoteAccess().authorize(actor, data['organization_id'])
        from django.shortcuts import get_object_or_404
        from integration_store.models import SourceSnapshot
        snapshot = get_object_or_404(SourceSnapshot.objects.select_related('row__batch'), row_id=data['row_id'], row__batch_id=data['batch_id'], row__batch__organization_id=data['organization_id'], row__batch__data_scope='synthetic', row__batch__status='published', row__batch__template__in=['physical', 'legal', 'accounts'])
        return Response({'actor_id': str(actor.pk), 'organization_id': str(data['organization_id']), 'batch_id': str(data['batch_id']), 'row_id': str(snapshot.row_id)})
