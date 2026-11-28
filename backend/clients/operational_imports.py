"""Transactional projection of reviewed physical-person source observations.

Only a trusted integration worker may call this service after verifying that the
rows are published snapshots from the specified organization and batch. This
module does not fetch data or expose an endpoint.
"""
from django.db import transaction
from rest_framework.exceptions import ValidationError

from audit.services import record
from iam_consumer.compat import Organization
from .import_mapping import physical_source, nonempty_contact_updates, physical_account_holder
from .models import Party, PhysicalPerson, LegalEntity, CRMProfile, OperationalPersonProjection, OperationalCompanyProjection, OperationalAccountProjection
from .workspace import ProfileInput, validate


from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from identity.policies import require
from internal_api.client import request_credentials, ServiceUnavailable


class OperationalJobStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id):
        from .models import OperationalImportJob
        from .source_mapping import peer
        organization_id = serializers.UUIDField().run_validation(request.query_params.get('organization_id'))
        require(request.user, 'clients.view', organization_id, full_scope=True)
        require(request.user, 'clients.view_financial', organization_id, full_scope=True)
        decision = peer().post('/internal/v1/operational-person/status-access', {
            'credentials': request_credentials(request), 'actor_id': str(request.user.pk),
            'organization_id': str(organization_id), 'batch_id': str(batch_id)})
        if decision != {'actor_id': str(request.user.pk), 'organization_id': str(organization_id), 'batch_id': str(batch_id)}:
            raise ServiceUnavailable()
        job = OperationalImportJob.objects.filter(batch_id=batch_id, organization_id=organization_id).first()
        return Response({'status': job.status if job else 'pending', 'processed': job.processed if job else 0, 'last_error': job.last_error if job else ''})


@transaction.atomic
def apply_physical_page(organization_id, batch_id, source_as_of, published_at, rows):
    Organization.objects.select_for_update().get(pk=organization_id)
    applied = 0
    for row in rows:
        try:
            source = physical_source(row['cells'], row['normalized_dates'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError('Données de personne source invalides.') from exc
        if row['source_id'] != source.source_id:
            raise ValidationError('La clé publiée ne correspond pas à la colonne B.')
        projection = OperationalPersonProjection.objects.select_for_update().filter(
            organization_id=organization_id, source_id=source.source_id).select_related('party').first()
        if projection:
            if projection.party.organization_id != organization_id:
                raise ValidationError('Organisation du dossier incompatible.')
            if projection.row_id == row['row_id'] or (source_as_of, published_at) <= (projection.source_as_of, projection.published_at):
                continue
            party = projection.party
            person = PhysicalPerson.objects.select_for_update().get(party=party)
            first = source.first_name or person.first_name
            last = source.last_name or person.last_name
            display = source.full_name or ' '.join(v for v in (first, last) if v)
            if len(first) > 100 or len(last) > 100 or len(display) > 200:
                raise ValidationError('Nom source trop long : revue requise.')
            if first != person.first_name or last != person.last_name:
                person.first_name, person.last_name = first, last
                person.save(update_fields=['first_name', 'last_name'])
            if display and display != party.display_name:
                party.display_name = display
                party.version += 1
                party.save(update_fields=['display_name', 'version'])
        else:
            display = source.full_name or ' '.join(v for v in (source.first_name, source.last_name) if v) or f'Identifiant source · {source.source_id}'
            if len(display) > 200 or len(source.first_name or '') > 100 or len(source.last_name or '') > 100:
                raise ValidationError('Nom source trop long : revue requise.')
            party = Party.objects.create(organization_id=organization_id, kind='physical', display_name=display, origin='OPERATIONAL_IMPORT')
            PhysicalPerson.objects.create(party=party, first_name=source.first_name or '', last_name=source.last_name or '')
            CRMProfile.objects.create(party=party)
            projection = OperationalPersonProjection(organization_id=organization_id, party=party, source_id=source.source_id)
        contact = nonempty_contact_updates(source)
        if contact:
            validated = validate(ProfileInput, {'version': 1, **contact}, partial=True)
            validated.pop('version')
            profile = CRMProfile.objects.select_for_update().get(party=party)
            for field, value in validated.items():
                setattr(profile, field, value)
            profile.version += 1
            profile.updated_by = None
            profile.save()
        if source.birth_date is not None:
            projection.birth_date = source.birth_date
        projection.batch_id = batch_id
        projection.row_id = row['row_id']
        projection.source_as_of = source_as_of
        projection.published_at = published_at
        projection.save()
        applied += 1
    if applied:
        record('clients.operational_import_projected', organization_id=organization_id,
               target_id=batch_id, context={'applied': applied})
    return applied


@transaction.atomic
def apply_company_page(organization_id, batch_id, source_as_of, published_at, rows):
    Organization.objects.select_for_update().get(pk=organization_id)
    applied = 0
    for row in rows:
        cells = row['cells']
        source_id = cells.get('2')
        if not isinstance(source_id, str) or not source_id or source_id != source_id.strip() or len(source_id) > 160 or row['source_id'] != source_id:
            raise ValidationError('Identifiant source de société invalide.')
        name = cells.get('4') or cells.get('3')
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
            raise ValidationError('Raison sociale source invalide.')
        projection = OperationalCompanyProjection.objects.select_for_update().filter(organization_id=organization_id, source_id=source_id).select_related('party').first()
        if projection:
            if projection.party.organization_id != organization_id:
                raise ValidationError('Organisation du dossier incompatible.')
            if projection.row_id == row['row_id'] or (source_as_of, published_at) <= (projection.source_as_of, projection.published_at):
                continue
            party = projection.party
            if name and party.display_name != name:
                company = LegalEntity.objects.select_for_update().get(party=party)
                company.legal_name = name
                company.save(update_fields=['legal_name'])
                party.display_name = name
                party.version += 1
                party.save(update_fields=['display_name', 'version'])
        else:
            display = name or f'Identifiant source · {source_id}'
            party = Party.objects.create(organization_id=organization_id, kind='legal', display_name=display, origin='OPERATIONAL_IMPORT')
            LegalEntity.objects.create(party=party, legal_name=name or '')
            CRMProfile.objects.create(party=party)
            projection = OperationalCompanyProjection(organization_id=organization_id, party=party, source_id=source_id)
        phone = cells.get('7') or cells.get('8')
        if phone is not None and phone != '':
            if not isinstance(phone, str):
                raise ValidationError('Téléphone source invalide.')
            if phone.strip():
                validated = validate(ProfileInput, {'version': 1, 'phone': phone}, partial=True)
                profile = CRMProfile.objects.select_for_update().get(party=party)
                profile.phone = validated['phone']
                profile.version += 1
                profile.updated_by = None
                profile.save()
        projection.batch_id, projection.row_id = batch_id, row['row_id']
        projection.source_as_of, projection.published_at = source_as_of, published_at
        projection.save()
        applied += 1
    if applied:
        record('clients.operational_import_projected', organization_id=organization_id,
               target_id=batch_id, context={'applied': applied, 'template': 'legal'})
    return applied


@transaction.atomic
def apply_account_page(organization_id, batch_id, source_as_of, published_at, rows):
    Organization.objects.select_for_update().get(pk=organization_id)
    applied = 0
    for row in rows:
        cells = row['cells']
        source_id = cells.get('5')
        if not isinstance(source_id, str) or not source_id or source_id != source_id.strip() or len(source_id) > 160 or row['source_id'] != source_id:
            raise ValidationError('Identifiant de compte source invalide.')
        try:
            holder_id = physical_account_holder(cells)
        except ValueError as exc:
            raise ValidationError('Détenteur source invalide : revue requise.') from exc
        projection = OperationalAccountProjection.objects.select_for_update().filter(organization_id=organization_id, source_id=source_id).first()
        if projection and (projection.row_id == row['row_id'] or (source_as_of, published_at) <= (projection.source_as_of, projection.published_at)):
            continue
        holder = OperationalPersonProjection.objects.filter(organization_id=organization_id, source_id=holder_id, party__organization_id=organization_id).first()
        if not holder:
            raise ValidationError('Détenteur physique introuvable : revue requise.')
        if projection and (projection.holder_id != holder_id or projection.party_id != holder.party_id):
            raise ValidationError('Changement de détenteur : revue requise.')
        if not projection:
            projection = OperationalAccountProjection(organization_id=organization_id, party=holder.party, source_id=source_id, holder_id=holder_id)
        projection.batch_id, projection.row_id = batch_id, row['row_id']
        projection.source_as_of, projection.published_at = source_as_of, published_at
        projection.save()
        applied += 1
    if applied:
        record('clients.operational_import_projected', organization_id=organization_id,
               target_id=batch_id, context={'applied': applied, 'template': 'accounts'})
    return applied
