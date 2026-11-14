from django.db import migrations

SQL = """
CREATE FUNCTION integration_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable integration record' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER immutable_staging BEFORE UPDATE OR DELETE ON ingestion_stagingrow
FOR EACH ROW EXECUTE FUNCTION integration_immutable();
CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON ingestion_sourcesnapshot
FOR EACH ROW EXECUTE FUNCTION integration_immutable();
CREATE TRIGGER immutable_journal BEFORE UPDATE OR DELETE ON integration_store_journal
FOR EACH ROW EXECUTE FUNCTION integration_immutable();
CREATE TRIGGER immutable_actor_reference BEFORE UPDATE OR DELETE ON integration_store_actorref
FOR EACH ROW EXECUTE FUNCTION integration_immutable();
CREATE TRIGGER immutable_org_reference BEFORE UPDATE OR DELETE ON integration_store_organizationref
FOR EACH ROW EXECUTE FUNCTION integration_immutable();
CREATE FUNCTION integration_outbox_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Outbox cannot be deleted' USING ERRCODE='23514'; END IF;
 IF NEW.event_id IS DISTINCT FROM OLD.event_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
  RAISE EXCEPTION 'Outbox identity is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER immutable_outbox BEFORE UPDATE OR DELETE ON integration_store_outbox
FOR EACH ROW EXECUTE FUNCTION integration_outbox_identity();
ALTER TABLE ingestion_importpolicy ADD CONSTRAINT integration_policy_org_id UNIQUE(organization_id,id);
ALTER TABLE ingestion_importbatch ADD CONSTRAINT integration_policy_same_org
 FOREIGN KEY(organization_id,policy_id) REFERENCES ingestion_importpolicy(organization_id,id)
 DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):
    dependencies = [("integration_store", "0001_initial")]
    # Additive journal retention: never automatically unapply a live schema.
    operations = [migrations.RunSQL(SQL)]
