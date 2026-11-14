"""Fail startup on unsafe credentials/schema rather than silently falling back."""

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def verify_connection(sender, connection, **kwargs):
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    if connection.vendor != "postgresql":
        raise ImproperlyConfigured("Commercial requires PostgreSQL")
    if __import__("os").environ.get("AICED_MIGRATION_ROLE"):
        return  # Offline deployment role, never provided to the runtime container.
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT current_schema(),rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,
            EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid),
            has_schema_privilege(current_user,'public','USAGE'),
            has_schema_privilege(current_user,%s,'CREATE'),
            has_database_privilege(current_user,current_database(),'TEMP')
            FROM pg_roles WHERE rolname=current_user""",
            [settings.COMMERCIAL_SCHEMA],
        )
        row = cursor.fetchone()
    if row != (
        settings.COMMERCIAL_SCHEMA,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ):
        connection.close()
        raise ImproperlyConfigured("Unsafe Commercial runtime database privileges")


class BoundaryConfig(AppConfig):
    name = "commercial_service"

    def ready(self):
        connection_created.connect(
            verify_connection, dispatch_uid="commercial_database_boundary"
        )
