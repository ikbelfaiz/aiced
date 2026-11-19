"""Local, synthetic-only background projection from published Integration batches."""
import logging
import threading
from uuid import UUID
from django.db import connection, transaction, close_old_connections
from django.utils import timezone
from rest_framework import serializers
from core.serializers import StrictSerializer
from .models import SyntheticImportJob
from .synthetic_imports import RowInput, apply_page
from .source_mapping import peer

log = logging.getLogger(__name__)
LOCK = 78109076125801


class WorkerPage(StrictSerializer):
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    template = serializers.ChoiceField(choices=['physical', 'legal', 'accounts'])
    source_as_of = serializers.DateField()
    published_at = serializers.DateTimeField()
    offset = serializers.IntegerField(min_value=0, max_value=50000)
    next_offset = serializers.IntegerField(allow_null=True, min_value=0, max_value=50000)
    rows = RowInput(many=True, max_length=20)


def discover(remote):
    offset = 0
    while offset is not None:
        data = remote.post('/internal/v1/source-mapping/synthetic-worker-discovery', {'offset': offset})
        batches = data.get('batches')
        if not isinstance(batches, list) or len(batches) > 100:
            raise ValueError('Invalid synthetic discovery response')
        for batch in batches:
            if set(batch) != {'batch_id', 'organization_id', 'template'} or batch['template'] not in ('physical', 'legal', 'accounts'):
                raise ValueError('Invalid synthetic batch metadata')
            batch_id, org_id = UUID(batch['batch_id']), UUID(batch['organization_id'])
            job, _ = SyntheticImportJob.objects.get_or_create(batch_id=batch_id, defaults={'organization_id': org_id, 'template': batch['template']})
            if job.organization_id != org_id or job.template != batch['template']:
                raise ValueError('Synthetic batch scope changed')
        next_offset = data.get('next_offset')
        if next_offset is not None and (type(next_offset) is not int or next_offset != offset + 100):
            raise ValueError('Invalid discovery cursor')
        offset = next_offset


def process(remote, batch_id):
    for _ in range(25):
        job = SyntheticImportJob.objects.get(batch_id=batch_id)
        if job.status == 'complete':
            return
        result = remote.post('/internal/v1/source-mapping/synthetic-worker-page', {'batch_id': str(job.batch_id), 'offset': job.next_offset})
        parser = WorkerPage(data=result)
        parser.is_valid(raise_exception=True)
        page = parser.validated_data
        if page['batch_id'] != job.batch_id or page['organization_id'] != job.organization_id or page['template'] != job.template or page['offset'] != job.next_offset:
            raise ValueError('Synthetic page scope changed')
        if page['next_offset'] is not None and (not page['rows'] or page['next_offset'] != job.next_offset + len(page['rows'])):
            raise ValueError('Invalid synthetic cursor')
        with transaction.atomic():
            job = SyntheticImportJob.objects.select_for_update().get(batch_id=batch_id)
            if job.status == 'complete':
                return
            if job.next_offset != page['offset']:
                raise ValueError('Synthetic cursor changed')
            apply_page(job.organization_id, job.batch_id, job.template, page['source_as_of'], page['published_at'], page['rows'])
            from audit.services import record
            record('clients.synthetic_import_synced', organization_id=job.organization_id, target_id=job.batch_id, context={'offset': page['offset'], 'count': len(page['rows']), 'template': job.template, 'actor': 'synthetic_background_worker'})
            job.processed += len(page['rows'])
            job.next_offset = page['next_offset'] if page['next_offset'] is not None else job.next_offset + len(page['rows'])
            job.status = 'complete' if page['next_offset'] is None else 'pending'
            job.last_error = ''
            job.save(update_fields=['processed', 'next_offset', 'status', 'last_error', 'updated_at'])
        if page['next_offset'] is None:
            return


def run_once():
    from core.synthetic_guard import require_synthetic_database
    require_synthetic_database()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [LOCK])
        if not cursor.fetchone()[0]:
            return
    try:
        remote = peer()
        discover(remote)
        ids = list(SyntheticImportJob.objects.exclude(status='complete').order_by('updated_at', 'batch_id').values_list('batch_id', flat=True)[:100])
        for batch_id in ids:
            try:
                process(remote, batch_id)
            except Exception:
                SyntheticImportJob.objects.filter(batch_id=batch_id).update(status='blocked', last_error='Synchronisation en attente : identifiant manquant, ambigu ou service indisponible.', attempts=models_f('attempts') + 1, updated_at=timezone.now())
                log.warning('Synthetic import job blocked; batch=%s', batch_id)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK])


def models_f(name):
    from django.db.models import F
    return F(name)


def run_loop(stop):
    while not stop.is_set():
        try:
            close_old_connections()
            run_once()
        except Exception:
            log.warning('Synthetic import worker unavailable; retry scheduled')
        finally:
            close_old_connections()
        stop.wait(5)


def start():
    stop = threading.Event()
    thread = threading.Thread(target=run_loop, args=(stop,), name='synthetic-import-worker', daemon=True)
    thread.start()
    return stop, thread
