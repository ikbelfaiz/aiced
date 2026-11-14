from django.db import migrations

SQL = """
CREATE FUNCTION aiced_client_scope_fence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM set_config('lock_timeout','5000ms',true);
  PERFORM pg_advisory_xact_lock_shared(4711239301896721);
  PERFORM pg_advisory_xact_lock(591445740000006);
  RETURN NULL;
END; $$;
CREATE FUNCTION aiced_client_reference_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) THEN
    IF TG_OP IN ('DELETE','TRUNCATE') THEN
      RAISE EXCEPTION 'Client references require retention; runtime hard deletion forbidden' USING ERRCODE='23514';
    ELSIF NEW.id IS DISTINCT FROM OLD.id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
      RAISE EXCEPTION 'Client id and organization are immutable' USING ERRCODE='23514';
    END IF;
  END IF;
  IF TG_OP='TRUNCATE' THEN RETURN NULL; END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER party_reference_guard BEFORE UPDATE OR DELETE ON clients_party
FOR EACH ROW EXECUTE FUNCTION aiced_client_reference_guard();
CREATE TRIGGER party_truncate_guard BEFORE TRUNCATE ON clients_party
FOR EACH STATEMENT EXECUTE FUNCTION aiced_client_reference_guard();
CREATE TRIGGER party_scope_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON clients_party
FOR EACH STATEMENT EXECUTE FUNCTION aiced_client_scope_fence();
CREATE TRIGGER prospect_scope_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON clients_prospect
FOR EACH STATEMENT EXECUTE FUNCTION aiced_client_scope_fence();
"""
REVERSE = """
DROP TRIGGER party_reference_guard ON clients_party;
DROP TRIGGER party_truncate_guard ON clients_party;
DROP FUNCTION aiced_client_reference_guard();
DROP TRIGGER prospect_scope_fence ON clients_prospect;
DROP TRIGGER party_scope_fence ON clients_party;
DROP FUNCTION aiced_client_scope_fence();
"""


class Migration(migrations.Migration):
    dependencies = [
        (
            "clients",
            "0007_alter_crmprofile_updated_by_alter_interaction_author_and_more",
        )
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
