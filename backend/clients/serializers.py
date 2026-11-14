from rest_framework import serializers
from core.serializers import StrictSerializer
from .models import Party, FinancialAccount


class PartySerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    assigned_to_id = serializers.UUIDField(read_only=True, allow_null=True)
    class Meta:
        model = Party
        fields = ['id', 'organization_id', 'kind', 'display_name', 'assigned_to_id', 'created_at']


class CRMUpdateSerializer(StrictSerializer):
    notes = serializers.CharField(max_length=5000, allow_blank=True, trim_whitespace=False)


class CRMProfileResponseSerializer(serializers.Serializer):
    party_id = serializers.UUIDField()
    notes = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()


class FinancialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialAccount
        fields = ['id', 'source', 'external_id', 'source_as_of', 'product_label']
