from rest_framework import serializers
from core.serializers import StrictSerializer
from .models import RoleAssignment


class LoginSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150, trim_whitespace=False)
    password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)


class GrantSerializer(StrictSerializer):
    membership_id = serializers.UUIDField()
    role_id = serializers.UUIDField()
    scope = serializers.ChoiceField(choices=RoleAssignment.Scope.choices)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class CreateUserSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)


class MembershipStateSerializer(StrictSerializer):
    is_active = serializers.BooleanField()


class CsrfResponseSerializer(serializers.Serializer):
    csrfToken = serializers.CharField()


class AccessAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    organization_name = serializers.CharField()
    scope = serializers.ChoiceField(choices=RoleAssignment.Scope.choices)
    expires_at = serializers.DateTimeField(allow_null=True)
    permissions = serializers.ListField(child=serializers.CharField())


class AccessResponseSerializer(serializers.Serializer):
    assignments = AccessAssignmentSerializer(many=True)


class RoleCatalogueSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=RoleAssignment.Scope.choices))
    permissions = serializers.ListField(child=serializers.CharField())
