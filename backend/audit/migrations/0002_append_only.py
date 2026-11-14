from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('''
          CREATE FUNCTION aiced_audit_immutable() RETURNS trigger AS $$
          BEGIN
            RAISE EXCEPTION 'Audit events are append-only' USING ERRCODE='23514';
          END; $$ LANGUAGE plpgsql;
          CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_auditevent
            FOR EACH ROW EXECUTE FUNCTION aiced_audit_immutable();
        ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP TRIGGER audit_append_only ON audit_auditevent; DROP FUNCTION aiced_audit_immutable();')


class Migration(migrations.Migration):
    dependencies = [('audit', '0001_initial')]
    operations = [migrations.RunPython(install, uninstall)]
