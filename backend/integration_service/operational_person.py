"""Private, bounded reader for published physical-person observations."""
import json
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from core.serializers import StrictSerializer
from internal_api.base import PrivateView
from internal_api.contracts import Credentials
from integration_store.models import ImportBatch, SourceSnapshot


class DiscoveryInput(StrictSerializer):
    offset = serializers.IntegerField(min_value=0, max_value=100000, default=0)


class PageInput(StrictSerializer):
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    offset = serializers.IntegerField(min_value=0, max_value=50000)


class StatusInput(StrictSerializer):
    credentials = Credentials()
    actor_id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()


def published_people():
    return ImportBatch.objects.filter(data_scope='operational', status='published',
        template__in=['physical', 'legal', 'accounts'], template_version=1, fixed_configuration_version=1)


class OperationalPersonDiscovery(PrivateView):
    audience = 'integration'

    def post(self, request):
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(DiscoveryInput, request)
        offset = data['offset']
        batches = list(published_people().order_by('published_at', 'id')[offset:offset + 101])
        return Response({'batches': [{'batch_id': str(batch.pk), 'organization_id': str(batch.organization_id), 'template': batch.template} for batch in batches[:100]],
                         'next_offset': offset + 100 if len(batches) > 100 else None})


class OperationalPersonPage(PrivateView):
    audience = 'integration'

    def post(self, request):
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(PageInput, request)
        batch = get_object_or_404(published_people(), pk=data['batch_id'], organization_id=data['organization_id'])
        snapshots = list(SourceSnapshot.objects.filter(row__batch=batch).select_related('row').order_by('row__number')[data['offset']:data['offset'] + 21])
        rows = []
        for snapshot in snapshots[:20]:
            cells = snapshot.row.cells
            allowed = {'physical': ('2', '3', '4', '5', '12', '13', '15'), 'legal': ('2', '3', '4', '7', '8'), 'accounts': ('4', '5')}[batch.template]
            item = {'row_id': str(snapshot.row_id), 'source_id': snapshot.external_key,
                    'cells': {key: cells[key] for key in allowed if key in cells},
                    'normalized_dates': {key: value for key, value in snapshot.row.normalized_dates.items() if key == '9' and batch.template == 'physical'}}
            if len(json.dumps([*rows, item]).encode('utf-8')) > 48000:
                if not rows:
                    raise ValidationError('Ligne trop volumineuse pour la synchronisation.')
                break
            rows.append(item)
        return Response({'batch_id': str(batch.pk), 'organization_id': str(batch.organization_id),
            'template': batch.template, 'source_as_of': batch.source_as_of, 'published_at': batch.published_at,
            'offset': data['offset'], 'next_offset': data['offset'] + len(rows) if len(snapshots) > len(rows) else None,
            'rows': rows})


class OperationalPersonStatusAccess(PrivateView):
    audience = 'integration'

    def post(self, request):
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(StatusInput, request)
        from integration_store.models import ActorRef
        from .access import RemoteAccess
        actor = ActorRef(pk=data['actor_id'])
        actor.credentials = data['credentials']
        RemoteAccess().authorize(actor, data['organization_id'])
        batch = get_object_or_404(published_people(), pk=data['batch_id'], organization_id=data['organization_id'])
        return Response({'actor_id': str(actor.pk), 'organization_id': str(batch.organization_id), 'batch_id': str(batch.pk)})
