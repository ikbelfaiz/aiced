from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from .security import authenticate


class PrivateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]  # HMAC mandatory in initial(), no session fallback.
    audience = "iam"

    def initial(self, request, *args, **kwargs):
        self.service = authenticate(request, self.audience)
        super().initial(request, *args, **kwargs)

    def validated(self, schema, request):
        serializer = schema(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
