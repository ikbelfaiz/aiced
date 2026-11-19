"""Fail closed unless this is the explicitly marked local demonstration database."""
from django.conf import settings
from django.db import connection
from rest_framework.exceptions import PermissionDenied


def require_synthetic_database():
    if not settings.DEBUG or connection.vendor != 'postgresql':
        raise PermissionDenied('Réservé à la base de démonstration synthétique.')
    with connection.cursor() as cursor:
        cursor.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=current_database()")
        row = cursor.fetchone()
    if not row or row[0] != 'aiced-s7-synthetic-only':
        raise PermissionDenied('Réservé à la base de démonstration synthétique.')
