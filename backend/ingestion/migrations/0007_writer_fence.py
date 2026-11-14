from django.db import migrations
from core.cutover_sql import install


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0006_runtimestate")]
    operations = [
        migrations.RunSQL(
            "INSERT INTO ingestion_runtimestate(id,mode) VALUES(1,'legacy');"
            + install(
                "public.ingestion_runtimestate",
                "legacy_import_writer_gate",
                [
                    "ingestion_importpolicy",
                    "ingestion_importbatch",
                    "ingestion_stagingrow",
                    "ingestion_sourcesnapshot",
                ],
                "legacy",
                591445740000001,
            )
        )
    ]
