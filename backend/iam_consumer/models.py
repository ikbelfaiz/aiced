"""Verified historical references; never an IAM authority or grant cache."""

import uuid
from django.db import models


class ActorRef(models.Model):
    id = models.UUIDField(primary_key=True)
    username = models.CharField(max_length=150)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True


class OrganizationRef(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=160)
    # This describes the last validated reference, not live access. HTTP grants
    # remain authoritative on every request and after write admission.
    is_active = models.BooleanField(default=True)


class MembershipRef(models.Model):
    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey(ActorRef, on_delete=models.PROTECT)
    organization = models.ForeignKey(OrganizationRef, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id", "organization"], name="crm_reference_membership_org"
            )
        ]


class InternalNonce(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)


class IAMJournalRef(models.Model):
    event_id = models.UUIDField(primary_key=True)


class CommercialJournalRef(models.Model):
    event_id = models.UUIDField(primary_key=True)
