\set ON_ERROR_STOP on
-- Run as the Integration table owner or a role authorised to grant its privileges.
-- Supply -v integration_runtime_role=THE_EXISTING_RUNTIME_ROLE to psql.
BEGIN;
SELECT set_config('aiced.fixed_config_runtime_role', :'integration_runtime_role', true);
DO $$
DECLARE
    runtime_name text := current_setting('aiced.fixed_config_runtime_role');
    runtime_oid oid;
    table_owner oid;
BEGIN
    SELECT oid INTO runtime_oid FROM pg_roles
      WHERE rolname = runtime_name AND rolcanlogin AND NOT rolsuper;
    IF runtime_oid IS NULL THEN
        RAISE EXCEPTION 'Runtime role must exist, be a login and not be a superuser';
    END IF;
    SELECT c.relowner INTO table_owner FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'aiced_integration' AND c.relname = 'ingestion_importbatch'
        AND c.relkind IN ('r', 'p');
    IF table_owner IS NULL OR table_owner = runtime_oid THEN
        RAISE EXCEPTION 'Integration table missing or runtime role owns it';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'aiced_integration' AND table_name = 'ingestion_importbatch'
         AND column_name = 'fixed_configuration_version') THEN
        RAISE EXCEPTION 'Apply integration_store.0006 before granting access';
    END IF;
END $$;
SELECT format('GRANT UPDATE (fixed_configuration_version) ON TABLE aiced_integration.ingestion_importbatch TO %I',
              current_setting('aiced.fixed_config_runtime_role')) \gexec
COMMIT;
