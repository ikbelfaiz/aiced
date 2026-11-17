from django.db import migrations,models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies=[('clients','0007_appointment'),('clients','0008_client_scope_fence'),('iam_consumer','0002_iamjournalref')]
    operations=[
        migrations.AlterField(model_name='appointment',name='owner',field=models.ForeignKey(to='iam_consumer.actorref',on_delete=django.db.models.deletion.PROTECT)),
        migrations.AlterField(model_name='appointment',name='organization',field=models.ForeignKey(to='iam_consumer.organizationref',on_delete=django.db.models.deletion.PROTECT)),
    ]
