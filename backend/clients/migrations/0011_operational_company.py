import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('clients', '0010_operational_person_projection')]
    operations = [
        migrations.AddField(model_name='operationalimportjob', name='template', field=models.CharField(default='physical', max_length=16)),
        migrations.CreateModel(name='OperationalCompanyProjection', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('organization_id', models.UUIDField()), ('source_id', models.CharField(max_length=160)),
            ('batch_id', models.UUIDField()), ('row_id', models.UUIDField()),
            ('source_as_of', models.DateField()), ('published_at', models.DateTimeField()),
            ('party', models.OneToOneField(to='clients.party', related_name='operational_company', on_delete=django.db.models.deletion.PROTECT)),
        ], options={'constraints': [models.UniqueConstraint(fields=['organization_id', 'source_id'], name='operational_company_source_unique')]}),
    ]
