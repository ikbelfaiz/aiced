from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integration_store", "0005_reusable_publication_rules")]
    operations = [
        migrations.AddField(model_name="importbatch", name="fixed_configuration_version", field=models.PositiveSmallIntegerField(null=True)),
        migrations.RemoveConstraint(model_name="importbatch", name="import_publication_consistent"),
        migrations.AddConstraint(model_name="importbatch", constraint=models.CheckConstraint(
            condition=(models.Q(status="staged", published_by__isnull=True, published_at__isnull=True, policy__isnull=True, fixed_configuration_version__isnull=True)
                       | models.Q(status="published", published_by__isnull=False, published_at__isnull=False, policy__isnull=False, fixed_configuration_version__isnull=True)
                       | models.Q(status="published", published_by__isnull=False, published_at__isnull=False, policy__isnull=True, fixed_configuration_version__isnull=False, fixed_configuration_version=1)),
            name="import_publication_consistent")),
    ]
