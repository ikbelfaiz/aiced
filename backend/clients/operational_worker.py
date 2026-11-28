"""Resumable projection of explicitly published operational person imports."""
import logging
import threading
from uuid import UUID
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework import serializers
from core.serializers import StrictSerializer
from .models import OperationalImportJob
from .operational_imports import apply_physical_page, apply_company_page, apply_account_page
from .source_mapping import peer

log = logging.getLogger(__name__)
LOCK = 78109076125802


class Row(StrictSerializer):
    row_id = serializers.UUIDField()
    source_id = serializers.CharField(max_length=160, trim_whitespace=False)
    cells = serializers.DictField()
    normalized_dates = serializers.DictField()


class Page(StrictSerializer):
    organization_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    template = serializers.ChoiceField(choices=['physical', 'legal', 'accounts'])
    source_as_of = serializers.DateField()
    published_at = serializers.DateTimeField()
    offset = serializers.IntegerField(min_value=0, max_value=50000)
    next_offset = serializers.IntegerField(allow_null=True, min_value=0, max_value=50000)
    rows = Row(many=True, max_length=20)


def discover(remote):
    offset = 0
    while offset is not None:
        response = remote.post('/internal/v1/operational-person/discovery', {'offset': offset})
        batches = response.get('batches')
        if not isinstance(batches, list) or len(batches) > 100:
            raise ValueError('Invalid discovery response')
        for item in batches:
            if set(item) != {'batch_id', 'organization_id', 'template'} or item['template'] not in ('physical', 'legal', 'accounts'):
                raise ValueError('Invalid batch metadata')
            batch_id, org_id = UUID(item['batch_id']), UUID(item['organization_id'])
            job, _ = OperationalImportJob.objects.get_or_create(batch_id=batch_id, defaults={'organization_id': org_id, 'template': item['template']})
            if job.organization_id != org_id or job.template != item['template']:
                raise ValueError('Batch organization changed')
        next_offset = response.get('next_offset')
        if next_offset is not None and (type(next_offset) is not int or next_offset != offset + 100):
            raise ValueError('Invalid discovery cursor')
        offset = next_offset


def process(remote, batch_id):
    for _ in range(25):
        job = OperationalImportJob.objects.get(batch_id=batch_id)
        if job.status == 'complete':
            return
        result = remote.post('/internal/v1/operational-person/page', {'batch_id': str(job.batch_id), 'organization_id': str(job.organization_id), 'offset': job.next_offset})
        serializer = Page(data=result)
        serializer.is_valid(raise_exception=True)
        page = serializer.validated_data
        if page['batch_id'] != job.batch_id or page['organization_id'] != job.organization_id or page['template'] != job.template or page['offset'] != job.next_offset:
            raise ValueError('Page scope changed')
        if page['next_offset'] is not None and (not page['rows'] or page['next_offset'] != page['offset'] + len(page['rows'])):
            raise ValueError('Invalid page cursor')
        with transaction.atomic():
            job = OperationalImportJob.objects.select_for_update().get(batch_id=batch_id)
            if job.status == 'complete':
                return
            if job.next_offset != page['offset'] or job.organization_id != page['organization_id'] or job.template != page['template']:
                raise ValueError('Job scope changed')
            apply = {'physical': apply_physical_page, 'legal': apply_company_page, 'accounts': apply_account_page}[job.template]
            apply(job.organization_id, job.batch_id, page['source_as_of'], page['published_at'], page['rows'])
            job.processed += len(page['rows'])
            job.next_offset = page['next_offset'] if page['next_offset'] is not None else page['offset'] + len(page['rows'])
            job.status = 'complete' if page['next_offset'] is None else 'pending'
            job.last_error = ''
            job.save(update_fields=['processed', 'next_offset', 'status', 'last_error', 'updated_at'])
        if page['next_offset'] is None:
            return


def run_once():
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [LOCK])
        if not cursor.fetchone()[0]:
            return
    try:
        remote = peer()
        discover(remote)
        for batch_id in OperationalImportJob.objects.exclude(status='complete').order_by('updated_at', 'batch_id').values_list('batch_id', flat=True)[:100]:
            try:
                process(remote, batch_id)
            except Exception:
                OperationalImportJob.objects.filter(batch_id=batch_id).update(status='blocked', last_error='Synchronisation en attente : données invalides ou service indisponible.', updated_at=timezone.now())
                log.warning('Operational import job blocked; batch=%s', batch_id)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK])


def run_loop(stop):
    while not stop.is_set():
        try:
            close_old_connections()
            run_once()
        except Exception:
            log.warning('Operational import worker unavailable; retry scheduled')
        finally:
            close_old_connections()
        stop.wait(5)


def start():
    stop = threading.Event()
    thread = threading.Thread(target=run_loop, args=(stop,), name='operational-import-worker', daemon=True)
    thread.start()
    return stop, thread
