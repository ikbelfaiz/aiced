from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''
        ALTER TABLE clients_party ADD CONSTRAINT party_assignment_same_org
        FOREIGN KEY (assigned_to_id, organization_id)
        REFERENCES identity_membership (id, organization_id) DEFERRABLE INITIALLY IMMEDIATE;

        CREATE FUNCTION aiced_check_party_subtype() RETURNS trigger AS $$
        DECLARE v_party_id uuid; party_kind varchar;
        BEGIN
          IF TG_TABLE_NAME = 'clients_party' THEN
            v_party_id := COALESCE(NEW.id, OLD.id);
          ELSE
            v_party_id := COALESCE(NEW.party_id, OLD.party_id);
          END IF;
          SELECT kind INTO party_kind FROM clients_party WHERE id=v_party_id;
          IF NOT FOUND THEN RETURN NULL; END IF;
          IF party_kind = 'physical' THEN
            IF NOT EXISTS (SELECT 1 FROM clients_physicalperson p WHERE p.party_id=v_party_id)
              OR EXISTS (SELECT 1 FROM clients_legalentity p WHERE p.party_id=v_party_id) THEN
              RAISE EXCEPTION 'Invalid physical party subtype' USING ERRCODE='23514';
            END IF;
          ELSE
            IF NOT EXISTS (SELECT 1 FROM clients_legalentity p WHERE p.party_id=v_party_id)
              OR EXISTS (SELECT 1 FROM clients_physicalperson p WHERE p.party_id=v_party_id) THEN
              RAISE EXCEPTION 'Invalid legal party subtype' USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NULL;
        END; $$ LANGUAGE plpgsql;
        CREATE CONSTRAINT TRIGGER party_subtype AFTER INSERT OR UPDATE ON clients_party
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION aiced_check_party_subtype();
        CREATE CONSTRAINT TRIGGER physical_subtype AFTER INSERT OR UPDATE OR DELETE ON clients_physicalperson
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION aiced_check_party_subtype();
        CREATE CONSTRAINT TRIGGER legal_subtype AFTER INSERT OR UPDATE OR DELETE ON clients_legalentity
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION aiced_check_party_subtype();
    ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('''
          DROP TRIGGER legal_subtype ON clients_legalentity;
          DROP TRIGGER physical_subtype ON clients_physicalperson;
          DROP TRIGGER party_subtype ON clients_party;
          DROP FUNCTION aiced_check_party_subtype();
          ALTER TABLE clients_party DROP CONSTRAINT party_assignment_same_org;
        ''')


class Migration(migrations.Migration):
    dependencies = [('clients', '0001_initial')]
    operations = [migrations.RunPython(install, uninstall)]
