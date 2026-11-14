from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('''
          CREATE FUNCTION aiced_subtype_identity_immutable() RETURNS trigger AS $$
          BEGIN
            IF NEW.party_id IS DISTINCT FROM OLD.party_id THEN
              RAISE EXCEPTION 'Subtype identity cannot be reassigned' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
          END; $$ LANGUAGE plpgsql;
          CREATE TRIGGER physical_identity BEFORE UPDATE OF party_id ON clients_physicalperson
            FOR EACH ROW EXECUTE FUNCTION aiced_subtype_identity_immutable();
          CREATE TRIGGER legal_identity BEFORE UPDATE OF party_id ON clients_legalentity
            FOR EACH ROW EXECUTE FUNCTION aiced_subtype_identity_immutable();
        ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('''
          DROP TRIGGER physical_identity ON clients_physicalperson;
          DROP TRIGGER legal_identity ON clients_legalentity;
          DROP FUNCTION aiced_subtype_identity_immutable();
        ''')


class Migration(migrations.Migration):
    dependencies = [('clients', '0002_scope_and_subtype_integrity')]
    operations = [migrations.RunPython(install, uninstall)]
