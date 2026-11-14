from rest_framework import serializers
from core.serializers import StrictSerializer


class Credentials(StrictSerializer):
    session_key = serializers.RegexField(r"^[a-z0-9]{32}$")
    method = serializers.ChoiceField(
        choices=["GET", "HEAD", "OPTIONS", "POST", "PATCH", "DELETE"]
    )
    csrf_cookie = serializers.CharField(
        max_length=128, required=False, allow_blank=True
    )
    csrf_token = serializers.CharField(max_length=128, required=False, allow_blank=True)
    origin = serializers.CharField(max_length=300, required=False, allow_blank=True)
    referer = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    host = serializers.CharField(max_length=255)
    scheme = serializers.ChoiceField(choices=["http", "https"])


class PrincipalInput(StrictSerializer):
    credentials = Credentials()
