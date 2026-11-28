import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('clients', '0009_synthetic_import_job')]
    operations = [migrations.CreateModel(name='OperationalPersonProjection', fields=[
        ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ('organization_id', models.UUIDField()), ('source_id', models.CharField(max_length=160)),
        ('batch_id', models.UUIDField()), ('row_id', models.UUIDField()),
        ('source_as_of', models.DateField()), ('published_at', models.DateTimeField()),
        ('birth_date', models.DateField(null=True)),
        ('party', models.OneToOneField(to='clients.party', related_name='operational_person', on_delete=django.db.models.deletion.PROTECT)),
    ], options={'constraints': [models.UniqueConstraint(fields=['organization_id', 'source_id'], name='operational_person_source_unique')]}),
    migrations.CreateModel(name='OperationalImportJob', fields=[
        ('batch_id', models.UUIDField(primary_key=True, serialize=False)),
        ('organization_id', models.UUIDField()), ('next_offset', models.PositiveIntegerField(default=0)),
        ('processed', models.PositiveIntegerField(default=0)), ('status', models.CharField(max_length=16, default='pending')),
        ('last_error', models.CharField(max_length=300, blank=True)), ('updated_at', models.DateTimeField(auto_now=True)),
    ])]
