from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [("iam_consumer", "0002_iamjournalref")]
    operations = [migrations.CreateModel(name="CommercialJournalRef", fields=[("event_id",models.UUIDField(primary_key=True,serialize=False))])]
