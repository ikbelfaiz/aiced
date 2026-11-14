from django.db import migrations

TABLES = [
    "identity_user",
    "identity_organization",
    "identity_capability",
    "identity_role",
    "identity_role_permissions",
    "identity_membership",
    "identity_roleassignment",
    "identity_loginbucket",
    "identity_internalnonce",
    "django_session",
    "audit_auditevent",
    "audit_auditoutbox",
    "audit_auditreceipt",
]


def install(apps, editor):
    editor.execute(
        """CREATE FUNCTION iam_writer_fence() RETURNS trigger LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
 BEGIN
 PERFORM pg_advisory_xact_lock_shared(591445740000003);
 IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AND NOT EXISTS(SELECT 1 FROM iam_control_runtimestate WHERE id=1 AND mode='service') THEN
 RAISE EXCEPTION 'IAM writer inactive' USING ERRCODE='42501'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$"""
    )
    for table in TABLES:
        editor.execute(
            f"CREATE TRIGGER iam_writer_fence BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION iam_writer_fence()"
        )


class Migration(migrations.Migration):
    dependencies = [("iam_control", "0002_boundaries")]
    operations = [migrations.RunPython(install)]
