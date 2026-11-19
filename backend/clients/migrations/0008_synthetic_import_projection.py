import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('clients', '0007_appointment'), ('identity', '0003_internal_authorization')]
    operations = [migrations.CreateModel(name='SyntheticImportProjection', fields=[
        ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ('template', models.CharField(max_length=16)), ('source_id', models.CharField(max_length=160)),
        ('batch_id', models.UUIDField()), ('row_id', models.UUIDField()),
        ('source_as_of', models.DateField()), ('published_at', models.DateTimeField()),
        ('cells', models.JSONField()),
        ('organization', models.ForeignKey(to='identity.organization', on_delete=django.db.models.deletion.PROTECT)),
        ('party', models.ForeignKey(to='clients.party', related_name='synthetic_imports', on_delete=django.db.models.deletion.PROTECT)),
    ], options={'constraints': [models.UniqueConstraint(fields=['organization', 'template', 'source_id'], name='synthetic_import_source_unique')]})]
