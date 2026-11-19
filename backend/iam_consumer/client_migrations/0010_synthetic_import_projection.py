import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('clients', '0009_appointment_refs'), ('clients', '0008_synthetic_import_projection'), ('iam_consumer', '0001_initial')]
    operations = [migrations.SeparateDatabaseAndState(state_operations=[migrations.AlterField(
        model_name='syntheticimportprojection', name='organization',
        field=models.ForeignKey(to='iam_consumer.organizationref', on_delete=django.db.models.deletion.PROTECT),
    )], database_operations=[migrations.RunSQL('''
        CREATE TABLE IF NOT EXISTS public.clients_syntheticimportprojection (
            id uuid PRIMARY KEY, template varchar(16) NOT NULL, source_id varchar(160) NOT NULL,
            batch_id uuid NOT NULL, row_id uuid NOT NULL, source_as_of date NOT NULL,
            published_at timestamptz NOT NULL, cells jsonb NOT NULL,
            organization_id uuid NOT NULL, party_id uuid NOT NULL REFERENCES public.clients_party(id) DEFERRABLE INITIALLY DEFERRED,
            CONSTRAINT synthetic_import_source_unique UNIQUE (organization_id, template, source_id)
        );
        DO $$ DECLARE c record; BEGIN
          FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='public.clients_syntheticimportprojection'::regclass AND contype='f' AND confrelid IN (to_regclass('public.identity_organization'), to_regclass('public.iam_consumer_organizationref')) LOOP
            EXECUTE format('ALTER TABLE public.clients_syntheticimportprojection DROP CONSTRAINT %I', c.conname);
          END LOOP;
          ALTER TABLE public.clients_syntheticimportprojection ADD CONSTRAINT synthetic_projection_org_fk FOREIGN KEY (organization_id) REFERENCES public.iam_consumer_organizationref(id) DEFERRABLE INITIALLY DEFERRED;
        END $$;
        CREATE INDEX IF NOT EXISTS synthetic_projection_party_idx ON public.clients_syntheticimportprojection(party_id);
        ''', reverse_sql=migrations.RunSQL.noop)])]
