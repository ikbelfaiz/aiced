from django.contrib.auth import authenticate
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError, Throttled
from audit.services import record
from .authentication import consume_login_budget, login_session, logout_session
from .models import Membership, Role, RoleAssignment
from .policies import grants, require, can_delegate
from .serializers import LoginSerializer, GrantSerializer, CreateUserSerializer, MembershipStateSerializer
from .serializers import CsrfResponseSerializer, AccessResponseSerializer, RoleCatalogueSerializer
from core.serializers import SessionResponseSerializer, ERROR_RESPONSES
from . import services


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: CsrfResponseSerializer})
    def get(self, request):
        return Response({'csrfToken': get_token(request)})


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: SessionResponseSerializer, **ERROR_RESPONSES})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not consume_login_budget(data['username'], request.META.get('REMOTE_ADDR', '')):
            record('login.throttled', result='denied', request=request)
            from django.conf import settings
            raise Throttled(wait=settings.LOGIN_WINDOW_SECONDS, detail='Trop de tentatives. Réessayez ultérieurement.')
        user = authenticate(request, username=data['username'], password=data['password'])
        if user is None:
            record('login.failed', result='denied', request=request)
            raise ValidationError({'detail': 'Identifiants invalides.'})
        login_session(request, user)
        return Response(SessionResponseSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None, **ERROR_RESPONSES})
    def post(self, request):
        logout_session(request)
        return Response(status=204)


class AccessView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: AccessResponseSerializer, **ERROR_RESPONSES})
    def get(self, request):
        # Self-discovery only; does not expose other employees' authorizations.
        return Response(AccessResponseSerializer({'assignments': [
            {'id': str(assignment.pk), 'organization_id': str(assignment.membership.organization_id),
             'organization_name': assignment.membership.organization.name,
             'scope': assignment.scope, 'expires_at': assignment.expires_at,
             'permissions': sorted(capability.code for capability in assignment.role.permissions.all())}
            for assignment in grants(request.user).select_related('membership__organization', 'role').prefetch_related('role__permissions').order_by('id')
        ]}).data)


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'user_id', 'username', 'organization_id', 'is_active']


class UserListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MembershipSerializer

    def get_queryset(self):
        org = self.kwargs['organization_id']
        require(self.request.user, 'users.manage', org, full_scope=True)
        return Membership.objects.filter(organization_id=org).select_related('user').order_by('id')

    @extend_schema(request=CreateUserSerializer, responses={201: MembershipSerializer, **ERROR_RESPONSES})
    def post(self, request, organization_id):
        require(request.user, 'users.manage', organization_id, full_scope=True)
        membership = services.create_user(request.user, organization_id, request.data, request)
        return Response(MembershipSerializer(membership).data, status=201)


class MembershipStateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=MembershipStateSerializer, responses={200: MembershipSerializer, **ERROR_RESPONSES})
    def patch(self, request, organization_id, membership_id):
        require(request.user, 'users.manage', organization_id, full_scope=True)
        membership = services.set_membership_state(request.user, organization_id, membership_id,
                                                   request.data, request)
        return Response(MembershipSerializer(membership).data)


class RoleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleAssignment
        fields = ['id', 'membership_id', 'role_id', 'scope', 'expires_at', 'is_active']


class RoleAssignmentView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RoleAssignmentSerializer

    def get_queryset(self):
        org = self.kwargs['organization_id']
        require(self.request.user, 'users.manage', org, full_scope=True)
        return RoleAssignment.objects.filter(membership__organization_id=org).order_by('id')

    @extend_schema(request=GrantSerializer, responses={201: RoleAssignmentSerializer, **ERROR_RESPONSES})
    def post(self, request, organization_id):
        require(request.user, 'users.manage', organization_id, full_scope=True)
        assignment = services.assign_role(request.user, organization_id, request.data, request)
        return Response(RoleAssignmentSerializer(assignment).data, status=201)


class RevokeRoleView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None, **ERROR_RESPONSES})
    def delete(self, request, organization_id, assignment_id):
        services.revoke_role(request.user, organization_id, assignment_id, request)
        return Response(status=204)


class RoleCatalogueView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: RoleCatalogueSerializer(many=True), **ERROR_RESPONSES})
    def get(self, request, organization_id):
        require(request.user, 'users.manage', organization_id, full_scope=True)
        roles = []
        for role in Role.objects.filter(is_active=True).prefetch_related('permissions').order_by('code'):
            scopes = list(RoleAssignment.Scope.values) if can_delegate(request.user, role, organization_id) else []
            if scopes:
                roles.append({'id': str(role.pk), 'name': role.name, 'scopes': scopes,
                              'permissions': sorted(capability.code for capability in role.permissions.all())})
        return Response(RoleCatalogueSerializer(roles, many=True).data)
