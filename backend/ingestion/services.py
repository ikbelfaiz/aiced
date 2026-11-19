import hashlib
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied, Throttled
from .runtime import record, authorize, model

ImportBatch, StagingRow, SourceSnapshot, ImportPolicy = [
    model(name)
    for name in ("ImportBatch", "StagingRow", "SourceSnapshot", "ImportPolicy")
]
from .templates import TEMPLATES, FIXED_CONFIGURATIONS
from .parser import parse


def stage(
    actor,
    organization_id,
    template,
    source_as_of,
    snapshot_kind,
    content,
    request=None,
    date_format="ISO",
    data_scope="legacy",
):
    authorize(actor, organization_id, "imports.upload")
    if not template:
        matches = []
        for candidate in TEMPLATES:
            try:
                parsed = parse(content, candidate, date_format)
            except ValidationError:
                continue
            matches.append((candidate, parsed))
        if len(matches) != 1:
            record("imports.file_rejected", actor=actor, organization_id=organization_id,
                   result="denied", request=request)
            raise ValidationError("Structure Excel non reconnue ou ambiguë.")
        template, detected_rows = matches[0]
    else:
        detected_rows = None
    if (
        template not in TEMPLATES
        or snapshot_kind not in ["partial", "complete"]
        or date_format not in ["ISO", "DMY"]
        or data_scope not in ["legacy", "synthetic", "operational"]
    ):
        raise ValidationError("Modèle ou nature du snapshot invalide.")
    if source_as_of > timezone.localdate():
        raise ValidationError("Date source future interdite.")
    digest = hashlib.sha256(content).hexdigest()
    key = dict(
        organization_id=organization_id,
        template=template,
        template_version=TEMPLATES[template]["version"],
        data_scope=data_scope,
        digest=digest,
        source_as_of=source_as_of,
        snapshot_kind=snapshot_kind,
        date_format=date_format,
    )
    existing = ImportBatch.objects.filter(**key).first()
    if existing:
        return existing, False
    try:
        rows = detected_rows if detected_rows is not None else parse(content, template, date_format)
    except ValidationError:
        record(
            "imports.file_rejected",
            actor=actor,
            organization_id=organization_id,
            result="denied",
            request=request,
        )
        raise
    for row in rows:
        for position, value in row["normalized_dates"].items():
            if datetime.fromisoformat(value).date() > source_as_of:
                row["errors"].append(
                    f"colonne {position} : date postérieure à la situation source déclarée"
                )
    with transaction.atomic():
        authorize(actor, organization_id, "imports.upload", lock=True, request=request)
        existing = ImportBatch.objects.filter(**key).first()
        if existing:
            return existing, False
        batches = ImportBatch.objects.filter(organization_id=organization_id)
        if (
            batches.filter(status="staged").count()
            >= settings.IMPORT_MAX_STAGED_BATCHES
            or batches.filter(created_at__date=timezone.localdate()).count()
            >= settings.IMPORT_MAX_DAILY_BATCHES
        ):
            raise Throttled(
                detail="Quota de lots atteint pour cette organisation. Contacter le responsable des données."
            )
        candidate_keys = list(
            {
                row["cells"][str(position)]
                for row in rows
                for position in [FIXED_CONFIGURATIONS[template]["key_column"]]
                if isinstance(row["cells"][str(position)], str)
            }
        )
        known = set()
        for start in range(0, len(candidate_keys), 500):
            known.update(
                SourceSnapshot.objects.filter(
                    row__batch__organization_id=organization_id,
                    row__batch__template=template,
                    row__batch__template_version=TEMPLATES[template]["version"],
                    row__batch__data_scope=data_scope,
                    external_key__in=candidate_keys[start : start + 500],
                ).values_list("external_key", flat=True)
            )
        for row in rows:
            for position in [FIXED_CONFIGURATIONS[template]["key_column"]]:
                if row["cells"][str(position)] in known:
                    row["warnings"].append(
                        f"Clé candidate colonne {position} déjà publiée : nouvelle version source à examiner, aucun rapprochement automatique"
                    )
        batch = ImportBatch.objects.create(**key, uploaded_by=actor)
        StagingRow.objects.bulk_create(
            [StagingRow(batch=batch, **row) for row in rows], batch_size=500
        )
        record(
            "imports.staged",
            actor=actor,
            organization_id=organization_id,
            target_id=batch.pk,
            request=request,
            context={
                "rows": len(rows),
                "rejected": sum(bool(row["errors"]) for row in rows),
                "template": template,
            },
        )
        return batch, True


@transaction.atomic
def create_policy(
    actor,
    organization_id,
    template,
    key_column,
    rationale,
    request=None,
    date_format="ISO",
    data_scope="legacy",
    template_version=None,
):
    authorize(
        actor, organization_id, "imports.policy_manage", lock=True, request=request
    )
    if (
        template not in TEMPLATES
        or key_column not in TEMPLATES[template]["candidate_keys"]
        or date_format not in ["ISO", "DMY"]
        or data_scope not in ["legacy", "synthetic", "operational"]
        or template_version not in [None, TEMPLATES.get(template, {}).get("version")]
    ):
        raise ValidationError("Colonne clé non prévue par le modèle.")
    configuration = dict(
        organization_id=organization_id,
        template=template,
        key_column=key_column,
        rationale=rationale.strip(),
        date_format=date_format,
        template_version=TEMPLATES[template]["version"],
        data_scope=data_scope,
    )
    # The existing organization mutation lock serializes proposals and approvals.
    existing = ImportPolicy.objects.filter(**configuration, revoked_at__isnull=True).order_by("created_at", "id").first()
    if existing:
        record("imports.policy_reused", actor=actor, organization_id=organization_id,
               target_id=existing.pk, request=request)
        return existing
    policy = ImportPolicy.objects.create(
        **configuration,
        created_by=actor,
    )
    record(
        "imports.policy_created",
        actor=actor,
        organization_id=organization_id,
        target_id=policy.pk,
        request=request,
    )
    return policy


@transaction.atomic
def approve_policy(actor, organization_id, policy_id, revoke=False, request=None):
    authorize(actor, organization_id, "imports.approve", lock=True, request=request)
    policy = get_object_or_404(
        ImportPolicy.objects.select_for_update(),
        pk=policy_id,
        organization_id=organization_id,
    )
    if revoke:
        if policy.revoked_at:
            return policy
        policy.revoked_at = timezone.now()
    else:
        if policy.created_by_id == actor.pk:
            raise PermissionDenied("Auto-approbation interdite.")
        if policy.revoked_at:
            raise ValidationError("Politique révoquée ; créer une nouvelle version.")
        if policy.approved_at:
            return policy
        if policy.data_scope != "legacy" and ImportPolicy.objects.filter(
            organization_id=organization_id, template=policy.template,
            template_version=policy.template_version, date_format=policy.date_format,
            data_scope=policy.data_scope, approved_at__isnull=False,
            revoked_at__isnull=True,
        ).exclude(pk=policy.pk).exists():
            raise ValidationError("Une règle approuvée est déjà active pour ce schéma, format et usage. Réutilisez-la, ou révoquez-la explicitement avant d’approuver une nouvelle configuration.")
        policy.approved_by = actor
        policy.approved_at = timezone.now()
    policy.save(
        update_fields=["revoked_at"] if revoke else ["approved_by", "approved_at"]
    )
    record(
        "imports.policy_revoked" if revoke else "imports.policy_approved",
        actor=actor,
        organization_id=organization_id,
        target_id=policy.pk,
        request=request,
    )
    return policy


@transaction.atomic
def publish(
    actor, organization_id, batch_id, policy_id=None, skip_rejected=False, request=None
):
    authorize(actor, organization_id, "imports.approve", lock=True, request=request)
    batch = get_object_or_404(
        ImportBatch.objects.select_for_update(),
        pk=batch_id,
        organization_id=organization_id,
    )
    if batch.uploaded_by_id == actor.pk:
        raise PermissionDenied("Le déposant ne peut pas publier son lot.")
    if batch.status == "published":
        if batch.policy_id != policy_id:
            raise ValidationError("Lot déjà publié avec une autre politique.")
        return batch
    policy = get_object_or_404(
        ImportPolicy.objects.select_for_update(),
        pk=policy_id,
        organization_id=organization_id,
        template=batch.template,
    )
    if not policy.approved_at or policy.revoked_at:
        raise ValidationError("Politique approuvée et active requise.")
    if policy.date_format != batch.date_format:
        raise ValidationError(
            "Le format de date du lot ne correspond pas à la règle approuvée."
        )
    if policy.template_version != batch.template_version or policy.data_scope != batch.data_scope:
        raise ValidationError("Schéma ou usage incompatible : les règles synthétiques, opérationnelles et historiques ne sont pas interchangeables.")
    rows = list(batch.rows.all())
    rejected = [row for row in rows if row.errors]
    if rejected and not skip_rejected:
        raise ValidationError(
            "Lignes rejetées : publication bloquée sans exclusion explicite."
        )
    accepted = [row for row in rows if not row.errors]
    if not accepted:
        raise ValidationError("Aucune ligne publiable.")
    keys = [row.cells.get(str(policy.key_column)) for row in accepted]
    if any(
        not isinstance(key, str) or not key.strip() or len(key) > 160 for key in keys
    ) or len(keys) != len(set(keys)):
        raise ValidationError(
            "Clé approuvée manquante ou dupliquée ; aucune publication."
        )
    SourceSnapshot.objects.bulk_create(
        [SourceSnapshot(row=row, external_key=key) for row, key in zip(accepted, keys)],
        batch_size=500,
    )
    batch.status = "published"
    batch.policy = policy
    batch.published_by = actor
    batch.published_at = timezone.now()
    batch.save(update_fields=["status", "policy", "published_by", "published_at"])
    record(
        "imports.published",
        actor=actor,
        organization_id=organization_id,
        target_id=batch.pk,
        request=request,
        context={
            "accepted": len(accepted),
            "excluded": len(rejected),
            "policy_id": str(policy.pk),
            "mode": "immutable_snapshots_only",
        },
    )
    return batch


@transaction.atomic
def publish_fixed(actor, organization_id, batch_id, skip_rejected=False, request=None):
    authorize(actor, organization_id, "imports.approve", lock=True, request=request)
    batch = get_object_or_404(ImportBatch.objects.select_for_update(), pk=batch_id, organization_id=organization_id)
    if batch.uploaded_by_id == actor.pk:
        raise PermissionDenied("Le déposant ne peut pas publier son lot.")
    if batch.status == "published":
        return batch
    if batch.data_scope == "legacy":
        policies = list(ImportPolicy.objects.filter(
            organization_id=organization_id, template=batch.template,
            template_version=batch.template_version, date_format=batch.date_format,
            data_scope="legacy", approved_at__isnull=False, revoked_at__isnull=True,
        ).order_by("id")[:2])
        if len(policies) != 1:
            raise ValidationError("Aucune règle historique unique approuvée : redéposez le fichier avec une classification explicite pour le revalider.")
        return publish(actor, organization_id, batch_id, policies[0].pk, skip_rejected, request)
    configuration = FIXED_CONFIGURATIONS.get(batch.template)
    if not configuration or batch.template_version != TEMPLATES[batch.template]["version"]:
        raise ValidationError("Configuration ou version de modèle non prise en charge.")
    rows = list(batch.rows.all())
    rejected = [row for row in rows if row.errors]
    if rejected and not skip_rejected:
        raise ValidationError("Lignes rejetées : exclusion explicite requise.")
    accepted = [row for row in rows if not row.errors]
    if not accepted:
        raise ValidationError("Aucune ligne publiable.")
    keys = [row.cells.get(str(configuration["key_column"])) for row in accepted]
    if any(not isinstance(key, str) or not key.strip() or key != key.strip() or len(key) > 160 for key in keys) or len(keys) != len(set(keys)):
        raise ValidationError("Clé fixe manquante ou dupliquée ; aucune publication.")
    SourceSnapshot.objects.bulk_create([SourceSnapshot(row=row, external_key=key) for row, key in zip(accepted, keys)], batch_size=500)
    batch.status = "published"
    batch.fixed_configuration_version = configuration["version"]
    batch.published_by = actor
    batch.published_at = timezone.now()
    batch.save(update_fields=["status", "fixed_configuration_version", "published_by", "published_at"])
    record("imports.published", actor=actor, organization_id=organization_id, target_id=batch.pk, request=request,
           context={"accepted": len(accepted), "excluded": len(rejected), "configuration": batch.template,
                    "configuration_version": configuration["version"], "key_column": configuration["key_column"],
                    "mode": "immutable_snapshots_only"})
    return batch
