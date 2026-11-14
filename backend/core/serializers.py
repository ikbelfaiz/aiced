from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Un objet JSON est requis.')
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: 'Champ non autorisé.' for key in sorted(unknown)})
        return super().to_internal_value(data)


class SessionResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    username = serializers.CharField()


class ErrorDetailSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    details = serializers.JSONField()


class APIErrorSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()


ERROR_RESPONSES = {code: APIErrorSerializer for code in (400, 403, 404, 406, 413, 415, 429)}
