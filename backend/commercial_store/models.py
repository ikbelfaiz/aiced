import uuid
from django.db import models


class PartyRef(models.Model):
    id = models.UUIDField(primary_key=True)
    organization_id = models.UUIDField()


class ActorRef(models.Model):
    id = models.UUIDField(primary_key=True)
    username = models.CharField(max_length=150)


class InternalNonce(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)


class RuntimeState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    mode = models.CharField(
        max_length=8,
        choices=[("service", "service"), ("legacy", "legacy"), ("frozen", "frozen")],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="commercial_gate_singleton"
            ),
            models.CheckConstraint(
                condition=models.Q(mode__in=["service", "legacy", "frozen"]),
                name="commercial_gate_mode",
            ),
        ]


class Opportunity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(
        PartyRef, on_delete=models.PROTECT, related_name="opportunities"
    )
    title = models.CharField(max_length=160)
    notes = models.TextField(max_length=5000, blank=True)
    # Manual commercial estimates, never holdings, valuation or a source balance.
    amount = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=[("TND", "TND")], default="TND")
    status = models.CharField(
        max_length=12, choices=[(v, v) for v in ["open", "won", "lost"]], default="open"
    )
    due_date = models.DateField(null=True, blank=True)
    author = models.ForeignKey(ActorRef, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clients_opportunity"
        ordering = ["-updated_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0) | models.Q(amount__isnull=True),
                name="opportunity_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["open", "won", "lost"]),
                name="opportunity_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency="TND"), name="opportunity_currency_tnd"
            ),
        ]


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
                name="commercial_audit_result",
            )
        ]


class Outbox(models.Model):
    event = models.OneToOneField(Journal, primary_key=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True)


class CampaignDraft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField()
    creator = models.ForeignKey(ActorRef, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    description = models.TextField(max_length=5000, blank=True)
    targeting_notes = models.TextField(max_length=2000, blank=True)
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, default='draft', editable=False)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', 'id']
        indexes = [models.Index(fields=['creator','organization_id','-updated_at'],name='campaign_creator_org_updated')]
        constraints = [
            models.CheckConstraint(condition=models.Q(status='draft'),name='campaign_draft_only'),
            models.CheckConstraint(condition=models.Q(version__gte=1),name='campaign_version_positive'),
            models.CheckConstraint(condition=models.Q(planned_start__isnull=True)|models.Q(planned_end__isnull=True)|models.Q(planned_end__gte=models.F('planned_start')),name='campaign_dates_order'),
        ]
