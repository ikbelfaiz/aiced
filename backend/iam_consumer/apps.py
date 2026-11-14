import os
from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.core.exceptions import ImproperlyConfigured


def verify(sender, connection, **kwargs):
    if os.environ.get("AICED_CONSUMER_MIGRATION") == "1":
        return
    with connection.cursor() as c:
        c.execute(
            """SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,
  EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid),
  has_schema_privilege(current_user,'aiced_iam','USAGE'),has_schema_privilege(current_user,'public','CREATE'),
  has_database_privilege(current_user,current_database(),'TEMP'),
  has_table_privilege(current_user,'public.identity_user','SELECT'),has_table_privilege(current_user,'public.django_session','SELECT')
  FROM pg_roles WHERE rolname=current_user"""
        )
        row = c.fetchone()
    if row != (False,) * 11:
        connection.close()
        raise ImproperlyConfigured("Unsafe IAM consumer database boundary")


class ConsumerConfig(AppConfig):
    name = "iam_consumer"

    def ready(self):
        connection_created.connect(verify, dispatch_uid="iam_consumer_boundary")
        from . import schema
