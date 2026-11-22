"""Descriptive management view of existing scopes; no management privilege grant."""
from datetime import datetime,time,timedelta
from django.db.models import Count,Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from identity.policies import organization_ids
from identity.models import Membership
from .policies import client_queryset
from .quality import summary
from .reporting import ActivityReport, ActivityReportFilters, CommercialActivityView, calculate
from .models import Interaction


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
    team=[]
    full_org_ids=list(organization_ids(actor,'clients.view',full_scope=True))
    if full_org_ids:
        visible_items=items
        memberships=Membership.objects.filter(
            organization_id__in=full_org_ids,
            is_active=True,
            user__is_active=True,
        ).select_related('organization','user').prefetch_related(
            'role_assignments__role__permissions'
        ).order_by('organization__name','user__username')
        for member in memberships:
            assignments=member.role_assignments.filter(is_active=True).filter(
                role__is_active=True,
                role__permissions__code='clients.view',
            ).filter(Q(expires_at__isnull=True)|Q(expires_at__gt=timezone.now()))
            if not assignments.exists():
                continue
            party_count=visible_items.filter(assigned_to_id=member.pk).count()
            interactions_count=None
            if metric_permission(actor,'interactions.view'):
                interactions_count=Interaction.objects.filter(
                    party__in=visible_items,
                    author_id=member.user_id,
                    occurred_at__gte=datetime.combine(values['date_from'],time.min,tzinfo=zone()),
                    occurred_at__lt=datetime.combine(values['date_to']+timedelta(days=1),time.min,tzinfo=zone()),
                ).count()
            team.append({
                'membership_id':str(member.pk),
                'username':member.user.username,
                'organization':member.organization.name,
                'clients':party_count,
                'interactions':interactions_count,
            })
    budget()
    result['portfolio']={'quality':quality,'by_kind':kinds,'team':team}
    return result


class ManagerialReport(ActivityReport):
    portfolio=serializers.DictField()


class ManagerialCRMView(CommercialActivityView):
    # Reuse the same admission, fresh IAM checks, deadline and DB error handling.
    calculation=staticmethod(calculate_managerial)

    @extend_schema(parameters=[ActivityReportFilters],responses={200:ManagerialReport})
    def get(self,request):
        return super().get(request)
