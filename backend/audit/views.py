from rest_framework import generics, serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from identity.policies import organization_ids
from .models import AuditEvent


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ['id', 'occurred_at', 'actor_id', 'organization_id', 'action', 'target_id', 'result', 'request_id', 'context']


class AuditListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AuditSerializer

    def get_queryset(self):
        organizations = organization_ids(self.request.user, 'audit.view', full_scope=True)
        if not organizations.exists():
            raise PermissionDenied('Opération non autorisée.')
        # NULL-organization authentication events require separate operator access, not exposed here.
        return AuditEvent.objects.filter(organization_id__in=organizations)
