import hashlib
import hmac
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import login, logout
from audit.services import record
from .models import LoginBucket
from .coordination import admit, barrier


@transaction.atomic
def login_session(request, user):
    admit(user)
    login(request, user)
    # Persist authenticated state in the audit transaction, rather than relying
    # only on SessionMiddleware saving it after the response.
    request.session.save()
    record('login.succeeded', actor=user, request=request)


@transaction.atomic
def logout_session(request):
    barrier(exclusive=True)
    actor = request.user
    logout(request)
    record('logout.succeeded', actor=actor, request=request)


def consume_login_budget(username, remote_address):
    now = timezone.now()
    allowed = True
    # Always lock IP before account. A blocked IP cannot grow account buckets.
    buckets = [(f'ip:{remote_address}', settings.LOGIN_IP_LIMIT),
               (f'account:{username.casefold()}', settings.LOGIN_ACCOUNT_LIMIT)]
    keyed = [(hmac.new(settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest(), limit)
             for raw, limit in buckets]
    with transaction.atomic():
        for key, limit in keyed:
            LoginBucket.objects.get_or_create(key=key, defaults={'started_at': now})
            bucket = LoginBucket.objects.select_for_update().get(pk=key)
            if (now - bucket.started_at).total_seconds() >= settings.LOGIN_WINDOW_SECONDS:
                bucket.started_at = now
                bucket.attempts = 0
            bucket.attempts += 1
            bucket.save(update_fields=['started_at', 'attempts'])
            allowed = allowed and bucket.attempts <= limit
            if not allowed:
                return False
    return allowed
