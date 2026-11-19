import uuid
from django.db import models

DATE_FORMAT_CHOICES = [("ISO", "ISO"), ("DMY", "Jour/mois/année")]


class RuntimeState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    mode = models.CharField(
        max_length=8,
        choices=[("legacy", "legacy"), ("service", "service"), ("frozen", "frozen")],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="owned_import_gate_singleton"
            ),
            models.CheckConstraint(
                condition=models.Q(mode__in=["legacy", "service", "frozen"]),
                name="owned_import_gate_mode",
            ),
        ]


class InternalNonce(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)


class ImportPolicy(models.Model):
    """An approved, versioned rule permits immutable snapshots only, never CRM merging."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "integration_store.OrganizationRef", on_delete=models.PROTECT
    )
    template = models.CharField(max_length=16)
    template_version = models.PositiveSmallIntegerField(default=1)
    data_scope = models.CharField(max_length=16, default="legacy", choices=[("legacy", "Non classifi\u00e9"), ("synthetic", "Synth\u00e9tique"), ("operational", "Op\u00e9rationnel")])
    key_column = models.PositiveSmallIntegerField()
    date_format = models.CharField(
        max_length=3,
        choices=DATE_FORMAT_CHOICES,
        default="ISO",
    )
    rationale = models.CharField(max_length=1000)
    created_by = models.ForeignKey(
        "integration_store.ActorRef", on_delete=models.PROTECT, related_name="+"
    )
    approved_by = models.ForeignKey(
        "integration_store.ActorRef",
        on_delete=models.PROTECT,
        null=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ingestion_importpolicy"
        constraints = [
            models.UniqueConstraint(fields=["organization", "template", "template_version", "date_format", "data_scope"], condition=models.Q(approved_at__isnull=False, revoked_at__isnull=True) & ~models.Q(data_scope="legacy"), name="policy_one_active_classified"),
            models.CheckConstraint(
                condition=models.Q(approved_by__isnull=True, approved_at__isnull=True)
                | models.Q(approved_by__isnull=False, approved_at__isnull=False),
                name="policy_approval_consistent",
            ),
            models.CheckConstraint(
                condition=~models.Q(created_by=models.F("approved_by")),
                name="policy_separate_approver",
            ),
        ]


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "integration_store.OrganizationRef", on_delete=models.PROTECT
    )
    template = models.CharField(max_length=16)
    data_scope = models.CharField(max_length=16, default="legacy", choices=[("legacy", "Non classifi\u00e9"), ("synthetic", "Synth\u00e9tique"), ("operational", "Op\u00e9rationnel")])
    template_version = models.PositiveSmallIntegerField(default=1)
    digest = models.CharField(max_length=64)
    source_as_of = models.DateField()
    snapshot_kind = models.CharField(max_length=10, default="partial")
    date_format = models.CharField(
        max_length=3,
        choices=DATE_FORMAT_CHOICES,
        default="ISO",
    )
    uploaded_by = models.ForeignKey(
        "integration_store.ActorRef", on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, default="staged")
    published_by = models.ForeignKey(
        "integration_store.ActorRef",
        on_delete=models.PROTECT,
        null=True,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True)
    policy = models.ForeignKey(ImportPolicy, on_delete=models.PROTECT, null=True)
    fixed_configuration_version = models.PositiveSmallIntegerField(null=True)

    class Meta:
        db_table = "ingestion_importbatch"
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "template",
                    "template_version",
                    "data_scope",
                    "digest",
                    "source_as_of",
                    "snapshot_kind",
                    "date_format",
                ],
                name="import_idempotency",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["staged", "published"]),
                name="import_status_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(uploaded_by=models.F("published_by")),
                name="import_separate_publisher",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status="staged",
                    published_by__isnull=True,
                    published_at__isnull=True,
                    policy__isnull=True,
                    fixed_configuration_version__isnull=True,
                )
                | models.Q(
                    status="published",
                    published_by__isnull=False,
                    published_at__isnull=False,
                    policy__isnull=False,
                    fixed_configuration_version__isnull=True,
                )
                | models.Q(
                    status="published", published_by__isnull=False,
                    published_at__isnull=False, policy__isnull=True,
                    fixed_configuration_version__isnull=False, fixed_configuration_version=1,
                ),
                name="import_publication_consistent",
            ),
        ]


class StagingRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.PROTECT, related_name="rows"
    )
    number = models.PositiveIntegerField()
    cells = models.JSONField()
    errors = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    normalized_dates = models.JSONField(default=dict)

    class Meta:
        db_table = "ingestion_stagingrow"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "number"], name="staging_row_unique"
            )
        ]


class SourceSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    row = models.OneToOneField(StagingRow, on_delete=models.PROTECT)
    external_key = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    # Values are immutable staging cells. No implicit Party/FinancialAccount link.

    class Meta:
        db_table = "ingestion_sourcesnapshot"


class OrganizationRef(models.Model):
    # Verified IAM UUID only; never a second identity authority.
    id = models.UUIDField(primary_key=True)


class ActorRef(models.Model):
    id = models.UUIDField(primary_key=True)

    @property
    def is_authenticated(self):
        return True


class Journal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_id = models.UUIDField(null=True)
    organization_id = models.UUIDField(null=True, db_index=True)
    action = models.CharField(max_length=100)
    target_id = models.UUIDField(null=True)
    result = models.CharField(
        max_length=20, choices=[("success", "success"), ("denied", "denied")]
    )
    request_id = models.UUIDField(default=uuid.uuid4)
    context = models.JSONField(default=dict)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(result__in=["success", "denied"]),
                name="integration_audit_result",
            )
        ]


class Outbox(models.Model):
    event = models.OneToOneField(Journal, primary_key=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True)
