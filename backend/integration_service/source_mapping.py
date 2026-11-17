"""Signed synthetic preview; real source reads are explicitly disabled."""
from .mapping_examples import preview, SCENARIOS


from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from core.serializers import StrictSerializer
from internal_api.base import PrivateView
from internal_api.contracts import Credentials
from integration_store.models import ActorRef
from .access import RemoteAccess


class MappingInput(StrictSerializer):
    credentials = Credentials()
    actor_id = serializers.UUIDField()
    organization_id = serializers.UUIDField()
    party_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=['synthetic', 'published'])
    scenario = serializers.ChoiceField(choices=SCENARIOS)


@extend_schema(exclude=True)
class MappingPreview(PrivateView):
    audience = 'integration'

    def post(self, request):
        if self.service != 'client_crm':
            raise PermissionDenied()
        data = self.validated(MappingInput, request)
        # No configuration switch or caller assertion can approve real visibility.
        if data['mode'] != 'synthetic':
            raise PermissionDenied('Mapping et visibilité source par objet non approuvés par AMEN INVEST.')
        actor = ActorRef(pk=data['actor_id'])
        actor.credentials = data['credentials']
        RemoteAccess().authorize(actor, data['organization_id'])
        return Response({**preview(data['scenario']), 'actor_id': str(actor.pk),
                         'organization_id': str(data['organization_id']), 'context_party_id': str(data['party_id'])})
