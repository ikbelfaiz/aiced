from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('clients', '0008_synthetic_import_projection')]
    operations = [migrations.CreateModel(name='SyntheticImportJob', fields=[
        ('batch_id', models.UUIDField(primary_key=True, serialize=False)),
        ('organization_id', models.UUIDField()), ('template', models.CharField(max_length=16)),
        ('status', models.CharField(max_length=16, default='pending')),
        ('next_offset', models.PositiveIntegerField(default=0)),
        ('processed', models.PositiveIntegerField(default=0)),
        ('attempts', models.PositiveIntegerField(default=0)),
        ('last_error', models.CharField(max_length=300, blank=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
    ])]
