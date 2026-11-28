import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('clients', '0011_operational_company')]
    operations = [migrations.CreateModel(name='OperationalAccountProjection', fields=[
        ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ('organization_id', models.UUIDField()), ('source_id', models.CharField(max_length=160)),
        ('holder_id', models.CharField(max_length=160)), ('batch_id', models.UUIDField()),
        ('row_id', models.UUIDField()), ('source_as_of', models.DateField()),
        ('published_at', models.DateTimeField()),
        ('party', models.ForeignKey(to='clients.party', related_name='operational_accounts', on_delete=django.db.models.deletion.PROTECT)),
    ], options={'constraints': [models.UniqueConstraint(fields=['organization_id', 'source_id'], name='operational_account_source_unique')]})]
