"""One-database revocation barrier. Shared admission, exclusive IAM changes.

Keep organization row locks BEFORE this barrier while the legacy writers exist.
RPC authorization readers never acquire it: the caller holds admission through
its local commit, including its local audit/outbox insert.
"""

from django.contrib.sessions.backends.db import SessionStore
from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from core.admission import AUTH_BARRIER, barrier, remote_write
from rest_framework.exceptions import PermissionDenied


def session_user(key):
    # Authorization readers must NEVER flush/rotate sessions while a caller is
    # holding shared admission; that would need the exclusive revocation lock.
    from .models import User

    row = Session.objects.filter(
        session_key=key, expire_date__gt=timezone.now()
    ).first()
    if row is None:
        raise PermissionDenied("Session révoquée ou expirée.")
    data = SessionStore().decode(row.session_data)
    user = User.objects.filter(pk=data.get("_auth_user_id"), is_active=True).first()
    if (
        user is None
        or data.get("_auth_user_backend") != "django.contrib.auth.backends.ModelBackend"
        or not constant_time_compare(
            data.get("_auth_user_hash", ""), user.get_session_auth_hash()
        )
    ):
        raise PermissionDenied("Identité révoquée.")
    return user


def admit(actor, request=None, exclusive=False):
    if getattr(settings, 'IAM_REMOTE', False):
        if exclusive: raise RuntimeError('Business service cannot mutate IAM')
        from iam_consumer.access import read_principal
        barrier()
        current = read_principal(actor.credentials)
        if current.pk != actor.pk: raise PermissionDenied('Identite invalide.')
        return
    if getattr(settings, 'IAM_OWNED', False):
        from iam_control.middleware import admit as gate
        gate(lock=True)
    barrier(exclusive)
    from .models import User

    current = User.objects.filter(pk=actor.pk, is_active=True).first()
    if current is None or not constant_time_compare(current.password, actor.password):
        raise PermissionDenied("Accès révoqué.")
    if request is not None:
        key = getattr(getattr(request, "session", None), "session_key", None)
        user = session_user(key)
        if not key or not user.is_authenticated or user.pk != actor.pk:
            raise PermissionDenied("Session révoquée ou expirée.")
