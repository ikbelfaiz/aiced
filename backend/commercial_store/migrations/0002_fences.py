from django.db import migrations

SQL = """
INSERT INTO commercial_store_runtimestate(id,mode) VALUES(1,'frozen');
CREATE FUNCTION commercial_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable Commercial record' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER journal_immutable BEFORE UPDATE OR DELETE ON commercial_store_journal FOR EACH ROW EXECUTE FUNCTION commercial_immutable();
CREATE TRIGGER party_reference_immutable BEFORE UPDATE OR DELETE ON commercial_store_partyref FOR EACH ROW EXECUTE FUNCTION commercial_immutable();
CREATE FUNCTION commercial_write_gate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_mode text;
BEGIN
  PERFORM pg_advisory_xact_lock_shared(591445740000007);
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) THEN
    SELECT mode INTO current_mode FROM aiced_commercial.commercial_store_runtimestate WHERE id=1;
    IF current_mode IS DISTINCT FROM 'service' THEN RAISE EXCEPTION 'Commercial writer fenced' USING ERRCODE='42501'; END IF;
  END IF;
  RETURN NULL;
END; $$;
CREATE TRIGGER commercial_opportunity_gate BEFORE INSERT OR UPDATE OR DELETE ON clients_opportunity FOR EACH STATEMENT EXECUTE FUNCTION commercial_write_gate();
CREATE TRIGGER commercial_journal_gate BEFORE INSERT ON commercial_store_journal FOR EACH STATEMENT EXECUTE FUNCTION commercial_write_gate();
CREATE TRIGGER commercial_outbox_gate BEFORE INSERT OR UPDATE OR DELETE ON commercial_store_outbox FOR EACH STATEMENT EXECUTE FUNCTION commercial_write_gate();
CREATE FUNCTION commercial_outbox_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' OR NEW.event_id IS DISTINCT FROM OLD.event_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'Immutable outbox identity' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER commercial_outbox_identity BEFORE UPDATE OR DELETE ON commercial_store_outbox FOR EACH ROW EXECUTE FUNCTION commercial_outbox_identity();
"""


class Migration(migrations.Migration):
    dependencies = [("commercial_store", "0001_initial")]
    operations = [migrations.RunSQL(SQL)]
