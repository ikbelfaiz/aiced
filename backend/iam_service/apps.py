from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.core.exceptions import ImproperlyConfigured
import os


def verify(sender, connection, **kwargs):
    if os.environ.get("AICED_MIGRATION_ROLE"):
        return
    with connection.cursor() as c:
        c.execute(
            """SELECT current_schema(),rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,
  EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid),
  has_schema_privilege(current_user,'public','USAGE'),has_schema_privilege(current_user,'aiced_iam','CREATE'),
  has_database_privilege(current_user,current_database(),'TEMP') FROM pg_roles WHERE rolname=current_user"""
        )
        row = c.fetchone()
    if row != (
        "aiced_iam",
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
        raise ImproperlyConfigured("Unsafe IAM database boundary")


class IAMConfig(AppConfig):
    name = "iam_service"

    def ready(self):
        connection_created.connect(verify, dispatch_uid="iam_owned_database_boundary")
