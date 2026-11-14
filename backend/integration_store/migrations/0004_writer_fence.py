from django.db import migrations
from core.cutover_sql import install


class Migration(migrations.Migration):
    dependencies = [("integration_store", "0003_internalnonce_runtimestate")]
    operations = [
        migrations.RunSQL(
            "INSERT INTO integration_store_runtimestate(id,mode) VALUES(1,'service');"
            + install(
                "integration_store_runtimestate",
                "owned_import_writer_gate",
                [
                    "ingestion_importpolicy",
                    "ingestion_importbatch",
                    "ingestion_stagingrow",
                    "ingestion_sourcesnapshot",
                ],
                "service",
                591445740000002,
            )
        )
    ]
