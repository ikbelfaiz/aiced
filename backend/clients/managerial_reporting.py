"""Descriptive management view of existing scopes; no management privilege grant."""
from django.db.models import Count
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from identity.policies import organization_ids
from .policies import client_queryset
from .quality import summary
from .reporting import ActivityReport, ActivityReportFilters, CommercialActivityView, calculate


def calculate_managerial(actor,values,budget):
    # A page name or reports.view_global is never an object access decision.
    if not organization_ids(actor,'clients.view'):raise PermissionDenied()
    def metric_permission(actor,code):
        # Capability presence in a different organization cannot enable an
        # activity panel. The existing object querysets still decide each row.
        return bool(set(organization_ids(actor,'clients.view')) & set(organization_ids(actor,code)))
    result=calculate(actor,values,budget,require_activity=False,metric_permission=metric_permission)
    items=client_queryset(actor,'clients.view').filter(prospect__isnull=True)
    budget()
    quality=summary(items)
    budget()
    kinds={kind:0 for kind in ['physical','legal']}
    for row in items.order_by().values('kind').annotate(count=Count('pk')):
        if row['kind'] not in kinds:
            from internal_api.client import ServiceUnavailable
            raise ServiceUnavailable('Type de client invalide.')
        kinds[row['kind']]=row['count']
    if sum(kinds.values())!=quality['total']:
        # Concurrent records may change between READ COMMITTED statements.
        # Never publish internally inconsistent counts as a common snapshot.
        from internal_api.client import ServiceUnavailable
        raise ServiceUnavailable('Le portefeuille a changé pendant le calcul.')
    budget()
    result['portfolio']={'quality':quality,'by_kind':kinds}
    return result


class ManagerialReport(ActivityReport):
    portfolio=serializers.DictField()


class ManagerialCRMView(CommercialActivityView):
    # Reuse the same admission, fresh IAM checks, deadline and DB error handling.
    calculation=staticmethod(calculate_managerial)

    @extend_schema(parameters=[ActivityReportFilters],responses={200:ManagerialReport})
    def get(self,request):
        return super().get(request)
