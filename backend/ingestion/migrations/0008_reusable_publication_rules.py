from django.db import migrations, models

SCOPES = [("legacy", "Non classifi\u00e9"), ("synthetic", "Synth\u00e9tique"), ("operational", "Op\u00e9rationnel")]

SQL = """
CREATE FUNCTION publication_rule_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Publication history cannot be deleted' USING ERRCODE='23514'; END IF;
 IF (NEW.id, NEW.organization_id, NEW.template, NEW.template_version, NEW.data_scope,
     NEW.key_column, NEW.date_format, NEW.rationale, NEW.created_by_id, NEW.created_at)
 IS DISTINCT FROM
    (OLD.id, OLD.organization_id, OLD.template, OLD.template_version, OLD.data_scope,
     OLD.key_column, OLD.date_format, OLD.rationale, OLD.created_by_id, OLD.created_at)
 OR (OLD.approved_at IS NOT NULL AND (NEW.approved_at, NEW.approved_by_id) IS DISTINCT FROM (OLD.approved_at, OLD.approved_by_id))
 OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
 THEN RAISE EXCEPTION 'Publication rule version is immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER immutable_publication_rule BEFORE UPDATE OR DELETE ON ingestion_importpolicy
FOR EACH ROW EXECUTE FUNCTION publication_rule_identity();
CREATE FUNCTION publication_batch_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.data_scope, NEW.template_version) IS DISTINCT FROM (OLD.data_scope, OLD.template_version)
 THEN RAISE EXCEPTION 'Import classification is immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER immutable_import_scope BEFORE UPDATE ON ingestion_importbatch
FOR EACH ROW EXECUTE FUNCTION publication_batch_scope();
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(SQL)


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0007_writer_fence")]
    operations = [
        migrations.AddField(model_name="importpolicy", name="template_version", field=models.PositiveSmallIntegerField(default=1)),
        migrations.AddField(model_name="importpolicy", name="data_scope", field=models.CharField(max_length=16, choices=SCOPES, default="legacy")),
        migrations.AddField(model_name="importbatch", name="data_scope", field=models.CharField(max_length=16, choices=SCOPES, default="legacy")),
        migrations.RemoveConstraint(model_name="importbatch", name="import_idempotency"),
        migrations.AddConstraint(model_name="importbatch", constraint=models.UniqueConstraint(fields=["organization", "template", "template_version", "data_scope", "digest", "source_as_of", "snapshot_kind", "date_format"], name="import_idempotency")),
        migrations.AddConstraint(model_name="importpolicy", constraint=models.UniqueConstraint(fields=["organization", "template", "template_version", "date_format", "data_scope"], condition=models.Q(approved_at__isnull=False, revoked_at__isnull=True) & ~models.Q(data_scope="legacy"), name="policy_one_active_classified")),
        migrations.RunPython(install),
    ]
