from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
    CREATE FUNCTION aiced_immutable_source() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Source snapshots and staging rows are immutable'; END; $$;
    CREATE TRIGGER immutable_staging BEFORE UPDATE OR DELETE ON ingestion_stagingrow
    FOR EACH ROW EXECUTE FUNCTION aiced_immutable_source();
    CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON ingestion_sourcesnapshot
    FOR EACH ROW EXECUTE FUNCTION aiced_immutable_source();
    """
    )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER immutable_staging ON ingestion_stagingrow; DROP TRIGGER immutable_snapshot ON ingestion_sourcesnapshot; DROP FUNCTION aiced_immutable_source();"
    )


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
