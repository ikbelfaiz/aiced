import importlib
from django.db import migrations


def install(apps, editor):
    mod = importlib.import_module("identity.migrations.0003_internal_authorization")
    mod.install(apps, editor)
    importlib.import_module("audit.migrations.0002_append_only").install(apps, editor)
    old = importlib.import_module("audit.migrations.0004_audit_outbox")
    for op in old.Migration.operations:
        if isinstance(op, migrations.RunSQL):
            editor.execute(op.sql)
    editor.execute("INSERT INTO iam_control_runtimestate(id,mode) VALUES(1,'frozen')")


class Migration(migrations.Migration):
    dependencies = [
        ("iam_control", "0001_initial"),
        ("identity", "0001_initial"),
        ("audit", "0002_initial"),
        ("sessions", "0001_initial"),
    ]
    operations = [migrations.RunPython(install)]
