"""Ports shared by the legacy deployment and the isolated Integration service.

Only the legacy adapter imports IAM models. Business rules/parser remain shared.
"""

from django.apps import apps
from django.conf import settings
from django.utils.module_loading import import_string


def model(name):
    return apps.get_model(getattr(settings, "IMPORT_MODEL_APP", "ingestion"), name)


def adapter():
    return import_string(
        getattr(settings, "IMPORT_ACCESS", "ingestion.runtime.LegacyAccess")
    )()


def record(*args, **kwargs):
    return adapter().record(*args, **kwargs)


def authorize(*args, **kwargs):
    return adapter().authorize(*args, **kwargs)


class LegacyAccess:
    def authorize(
        self,
        actor,
        organization_id,
        capability="imports.view",
        lock=False,
        request=None,
    ):
        from identity.coordination import admit
        from identity.models import Organization
        from identity.policies import require

        require(actor, "imports.view", organization_id, full_scope=True)
        require(actor, "clients.view_financial", organization_id, full_scope=True)
        require(actor, capability, organization_id, full_scope=True)
        if lock:
            Organization.objects.select_for_update().get(pk=organization_id)
            admit(actor, request)
            self.authorize(actor, organization_id, capability)

    def record(self, *args, **kwargs):
        from audit.services import record

        return record(*args, **kwargs)

    def history(self, organization_id, batch_id):
        from audit.models import AuditEvent

        return AuditEvent.objects.filter(
            organization_id=organization_id, target_id=batch_id
        ).order_by("occurred_at")[:100]

    def context(self, actor):
        from identity.models import Organization
        from identity.policies import organization_ids

        orgs = Organization.objects.filter(
            pk__in=organization_ids(actor, "imports.view", True)
        ).filter(pk__in=organization_ids(actor, "clients.view_financial", True))

        def can(code, org):
            return (
                organization_ids(actor, code, True)
                .filter(membership__organization_id=org.pk)
                .exists()
            )

        return [
            {
                "id": org.pk,
                "name": org.name,
                **{
                    name: can(code, org)
                    for name, code in (
                        ("upload", "imports.upload"),
                        ("approve", "imports.approve"),
                        ("policy_manage", "imports.policy_manage"),
                        ("create_client", "clients.create"),
                    )
                },
            }
            for org in orgs
        ]
