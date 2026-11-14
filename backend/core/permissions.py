from rest_framework.permissions import BasePermission


class DenyAll(BasePermission):
    message = 'Cette opération ne dispose pas encore de politique autorisée.'

    def has_permission(self, request, view):
        return False
