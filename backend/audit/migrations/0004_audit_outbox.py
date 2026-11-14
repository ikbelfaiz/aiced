import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0003_auditevent_context")]
    operations = [
        migrations.CreateModel(
            name="AuditOutbox",
            fields=[
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        primary_key=True,
                        serialize=False,
                        to="audit.auditevent",
                    ),
                ),
                ("producer", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delivered_at", models.DateTimeField(null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="AuditReceipt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("producer", models.CharField(max_length=20)),
                ("event_id", models.UUIDField()),
                ("digest", models.CharField(max_length=64)),
                ("payload", models.JSONField()),
                ("received_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("producer", "event_id"),
                        name="audit_receipt_producer_event",
                    )
                ]
            },
        ),
        migrations.RunSQL(
            "CREATE TRIGGER audit_receipt_append_only BEFORE UPDATE OR DELETE ON audit_auditreceipt FOR EACH ROW EXECUTE FUNCTION aiced_audit_immutable()",
            "DROP TRIGGER audit_receipt_append_only ON audit_auditreceipt",
        ),
        migrations.RunSQL(
            """
          CREATE FUNCTION aiced_outbox_identity_immutable() RETURNS trigger AS $$
          BEGIN
            IF TG_OP = 'DELETE' OR NEW.event_id IS DISTINCT FROM OLD.event_id
               OR NEW.producer IS DISTINCT FROM OLD.producer
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
              RAISE EXCEPTION 'Outbox identity is immutable' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
          END; $$ LANGUAGE plpgsql;
          CREATE TRIGGER audit_outbox_identity BEFORE UPDATE OR DELETE ON audit_auditoutbox
            FOR EACH ROW EXECUTE FUNCTION aiced_outbox_identity_immutable();
        """,
            "DROP TRIGGER audit_outbox_identity ON audit_auditoutbox; DROP FUNCTION aiced_outbox_identity_immutable()",
        ),
    ]
