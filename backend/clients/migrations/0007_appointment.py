import uuid
from django.conf import settings
from django.db import migrations,models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies=[('clients','0006_prospect'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[migrations.CreateModel(name='Appointment',fields=[
        ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
        ('title',models.CharField(max_length=160)),
        ('kind',models.CharField(max_length=16,choices=[('call','call'),('email','email'),('meeting','meeting'),('visit','visit')])),
        ('notes',models.TextField(blank=True,max_length=5000)),('starts_at',models.DateTimeField()),('ends_at',models.DateTimeField()),
        ('version',models.PositiveIntegerField(default=1)),('updated_at',models.DateTimeField(auto_now=True)),
        ('organization',models.ForeignKey(to='identity.organization',on_delete=django.db.models.deletion.PROTECT)),
        ('owner',models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT)),
    ],options={'ordering':['starts_at','id'],'indexes':[models.Index(fields=['owner','organization','starts_at'],name='agenda_owner_org_start')],
        'constraints':[models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')),name='appointment_positive_duration'),models.CheckConstraint(condition=models.Q(kind__in=['call','email','meeting','visit']),name='appointment_kind_valid')]}),
    migrations.RunSQL("""
    CREATE FUNCTION public.appointment_scope_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'Immutable appointment scope' USING ERRCODE='23514';
      END IF; RETURN NEW;
    END $$;
    CREATE TRIGGER appointment_scope_immutable BEFORE UPDATE ON clients_appointment FOR EACH ROW EXECUTE FUNCTION public.appointment_scope_immutable();
    ""","DROP TRIGGER appointment_scope_immutable ON clients_appointment; DROP FUNCTION public.appointment_scope_immutable();")]
