from django.conf import settings

if getattr(settings, "IAM_REMOTE", False):
    from .models import OrganizationRef as Organization
else:
    from identity.models import Organization
