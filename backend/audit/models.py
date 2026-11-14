import uuid
from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(getattr(settings, "BUSINESS_ACTOR_MODEL", settings.AUTH_USER_MODEL), null=True, on_delete=models.PROTECT)
    organization = models.ForeignKey(getattr(settings, 'BUSINESS_ORGANIZATION_MODEL', 'identity.Organization'), null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=100, db_index=True)
    target_id = models.UUIDField(null=True)
    result = models.CharField(max_length=20, choices=[('success', 'Succès'), ('denied', 'Refus')])
    request_id = models.UUIDField(default=uuid.uuid4)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        constraints = [models.CheckConstraint(condition=models.Q(result__in=['success', 'denied']), name='audit_result_valid')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('Les événements audit sont immuables.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Les événements audit sont immuables.')


class AuditOutbox(models.Model):
    # Event stays local and immutable; delivery state is separate and mutable.
    event = models.OneToOneField(AuditEvent, primary_key=True, on_delete=models.PROTECT)
    producer = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)


class AuditReceipt(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    producer = models.CharField(max_length=20)
    event_id = models.UUIDField()
    digest = models.CharField(max_length=64)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['producer','event_id'],name='audit_receipt_producer_event')]
