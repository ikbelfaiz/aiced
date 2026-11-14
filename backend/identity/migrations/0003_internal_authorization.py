from django.db import migrations, models


FORWARD = """
CREATE FUNCTION aiced_auth_revocation_barrier() RETURNS trigger AS $$
BEGIN
  PERFORM set_config('lock_timeout','5000ms',true);
  PERFORM pg_advisory_xact_lock(4711239301896721);
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER auth_user_barrier BEFORE UPDATE OF is_active, password OR DELETE ON identity_user
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_org_barrier BEFORE UPDATE OF is_active OR DELETE ON identity_organization
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_membership_barrier BEFORE UPDATE OR DELETE ON identity_membership
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_role_barrier BEFORE UPDATE OR DELETE ON identity_role
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_assignment_barrier BEFORE INSERT OR UPDATE OR DELETE ON identity_roleassignment
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_capability_barrier BEFORE UPDATE OR DELETE ON identity_capability
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_permissions_barrier BEFORE INSERT OR UPDATE OR DELETE ON identity_role_permissions
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
CREATE TRIGGER auth_session_barrier BEFORE UPDATE OR DELETE ON django_session
 FOR EACH ROW EXECUTE FUNCTION aiced_auth_revocation_barrier();
"""


def install(apps, schema_editor):
    schema_editor.execute(FORWARD)


def uninstall(apps, schema_editor):
    for name, table in [
        ("user", "identity_user"),
        ("org", "identity_organization"),
        ("membership", "identity_membership"),
        ("role", "identity_role"),
        ("assignment", "identity_roleassignment"),
        ("capability", "identity_capability"),
        ("permissions", "identity_role_permissions"),
        ("session", "django_session"),
    ]:
        schema_editor.execute(f"DROP TRIGGER auth_{name}_barrier ON {table}")
    schema_editor.execute("DROP FUNCTION aiced_auth_revocation_barrier()")


class Migration(migrations.Migration):
    dependencies = [
        (
            "identity",
            "0002_capability_loginbucket_organization_membership_role_and_more",
        ),
        ("sessions", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="InternalNonce",
            fields=[
                (
                    "digest",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.RunPython(install, uninstall),
    ]
