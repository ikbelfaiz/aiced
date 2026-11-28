import uuid
from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual


class Party(models.Model):
    class Kind(models.TextChoices):
        PHYSICAL = 'physical', 'Personne physique'
        LEGAL = 'legal', 'Personne morale'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(getattr(settings, 'BUSINESS_ORGANIZATION_MODEL', 'identity.Organization'), on_delete=models.PROTECT)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    display_name = models.CharField(max_length=200)
    assigned_to = models.ForeignKey(getattr(settings, 'BUSINESS_MEMBERSHIP_MODEL', 'identity.Membership'), null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    origin = models.CharField(max_length=60, default='SYNTHETIC_ONLY')
    version = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=['organization', 'assigned_to'])]
        constraints = [models.CheckConstraint(condition=models.Q(kind__in=['physical', 'legal']), name='party_kind_valid')]


class Prospect(models.Model):
    """Local qualification only; never an authoritative source identity or balance."""
    class Status(models.TextChoices):
        CONTACT = 'contact', 'À contacter'
        QUALIFIED = 'qualified', 'Qualifié'
        DISCUSSION = 'discussion', 'En discussion'
        FOLLOW_UP = 'follow_up', 'À relancer'
        CLOSED = 'closed', 'Clos'

    party = models.OneToOneField(Party, primary_key=True, on_delete=models.PROTECT)
    source = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONTACT)
    next_action = models.CharField(max_length=160, blank=True)
    next_action_date = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['contact', 'qualified', 'discussion', 'follow_up', 'closed']), name='prospect_status_valid'),
            models.CheckConstraint(condition=models.Q(next_action_date__isnull=True) | ~models.Q(next_action=''), name='prospect_action_date_requires_label'),
        ]


class PhysicalPerson(models.Model):
    party = models.OneToOneField(Party, primary_key=True, on_delete=models.PROTECT)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)


class LegalEntity(models.Model):
    party = models.OneToOneField(Party, primary_key=True, on_delete=models.PROTECT)
    legal_name = models.CharField(max_length=200)


class CRMProfile(models.Model):
    party = models.OneToOneField(Party, primary_key=True, on_delete=models.PROTECT, related_name='crm_profile')
    notes = models.TextField(blank=True, max_length=5000)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(getattr(settings, "BUSINESS_ACTOR_MODEL", settings.AUTH_USER_MODEL), null=True, on_delete=models.PROTECT)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    profession = models.CharField(max_length=120, blank=True)
    sector = models.CharField(max_length=120, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.CheckConstraint(condition=LessThanOrEqual(Length('notes'), 5000), name='crm_notes_length')]


class ExternalIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(Party, on_delete=models.PROTECT)
    source = models.CharField(max_length=60)
    external_id = models.CharField(max_length=160)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source', 'external_id'], name='external_identity_unique')]


class SyntheticImportProjection(models.Model):
    """A client-side copy of an explicitly synthetic published source row."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(getattr(settings, 'BUSINESS_ORGANIZATION_MODEL', 'identity.Organization'), on_delete=models.PROTECT)
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='synthetic_imports')
    template = models.CharField(max_length=16)
    source_id = models.CharField(max_length=160)
    batch_id = models.UUIDField()
    row_id = models.UUIDField()
    source_as_of = models.DateField()
    published_at = models.DateTimeField()
    cells = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['organization', 'template', 'source_id'], name='synthetic_import_source_unique')]


class SyntheticImportJob(models.Model):
    batch_id = models.UUIDField(primary_key=True)
    organization_id = models.UUIDField()
    template = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default='pending')
    next_offset = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class OperationalPersonProjection(models.Model):
    """Latest applied physical-person observation, separate from CRM fields."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField()
    party = models.OneToOneField(Party, on_delete=models.PROTECT, related_name='operational_person')
    source_id = models.CharField(max_length=160)
    batch_id = models.UUIDField()
    row_id = models.UUIDField()
    source_as_of = models.DateField()
    published_at = models.DateTimeField()
    birth_date = models.DateField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['organization_id', 'source_id'], name='operational_person_source_unique')]


class OperationalImportJob(models.Model):
    batch_id = models.UUIDField(primary_key=True)
    organization_id = models.UUIDField()
    template = models.CharField(max_length=16, default='physical')
    next_offset = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, default='pending')
    last_error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class OperationalCompanyProjection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField()
    party = models.OneToOneField(Party, on_delete=models.PROTECT, related_name='operational_company')
    source_id = models.CharField(max_length=160)
    batch_id = models.UUIDField()
    row_id = models.UUIDField()
    source_as_of = models.DateField()
    published_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['organization_id', 'source_id'], name='operational_company_source_unique')]


class OperationalAccountProjection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField()
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='operational_accounts')
    source_id = models.CharField(max_length=160)
    holder_id = models.CharField(max_length=160)
    batch_id = models.UUIDField()
    row_id = models.UUIDField()
    source_as_of = models.DateField()
    published_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['organization_id', 'source_id'], name='operational_account_source_unique')]


class FinancialAccount(models.Model):
    # Local source-owned projection only. No API writer or integration in Phase 1.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='accounts')
    source = models.CharField(max_length=60)
    external_id = models.CharField(max_length=160)
    source_as_of = models.DateTimeField()
    product_label = models.CharField(max_length=120)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source', 'external_id'], name='financial_account_source_unique')]


class Interaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='interactions')
    kind = models.CharField(max_length=16, choices=[(v, v) for v in ['call', 'email', 'meeting', 'visit']])
    subject = models.CharField(max_length=160)
    notes = models.TextField(max_length=5000, blank=True)
    occurred_at = models.DateTimeField()
    author = models.ForeignKey(getattr(settings, "BUSINESS_ACTOR_MODEL", settings.AUTH_USER_MODEL), on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-occurred_at', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(kind__in=['call','email','meeting','visit']), name='interaction_kind_valid')]


class Appointment(models.Model):
    """Personal planned activity; never a completed Interaction or source record."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(getattr(settings,'BUSINESS_ORGANIZATION_MODEL','identity.Organization'),on_delete=models.PROTECT)
    owner = models.ForeignKey(getattr(settings,'BUSINESS_ACTOR_MODEL',settings.AUTH_USER_MODEL),on_delete=models.PROTECT)
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=16,choices=Interaction._meta.get_field('kind').choices)
    notes = models.TextField(max_length=5000,blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering=['starts_at','id']
        indexes=[models.Index(fields=['owner','organization','starts_at'],name='agenda_owner_org_start')]
        constraints=[models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')),name='appointment_positive_duration'),models.CheckConstraint(condition=models.Q(kind__in=['call','email','meeting','visit']),name='appointment_kind_valid')]


class Opportunity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='opportunities')
    title = models.CharField(max_length=160)
    notes = models.TextField(max_length=5000, blank=True)
    # Manual commercial estimates, never holdings, valuation or a source balance.
    amount = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=[('TND', 'TND')], default='TND')
    status = models.CharField(max_length=12, choices=[(v,v) for v in ['open','won','lost']], default='open')
    due_date = models.DateField(null=True, blank=True)
    author = models.ForeignKey(getattr(settings, "BUSINESS_ACTOR_MODEL", settings.AUTH_USER_MODEL), on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gte=0) | models.Q(amount__isnull=True), name='opportunity_amount_nonnegative'), models.CheckConstraint(condition=models.Q(status__in=['open','won','lost']), name='opportunity_status_valid'), models.CheckConstraint(condition=models.Q(currency='TND'), name='opportunity_currency_tnd')]
