"""Explicit pairwise trust: ingress verification is never an outbound identity."""

from django.core.exceptions import ImproperlyConfigured


def validate(keys, outbound):
    selected = keys.get(outbound)
    if (
        not selected
        or selected.get("service") != "client_crm"
        or "iam" not in selected.get("audiences", [])
    ):
        raise ImproperlyConfigured("Client requires its own IAM signing identity")
    for key in keys.values():
        own = (
            key.get("service") == "client_crm"
            and bool(key.get("audiences"))
            and set(key["audiences"]) <= {"iam", "audit", "integration", "commercial"}
        )
        ingress = key.get("service") == "commercial" and key.get("audiences") == [
            "client"
        ]
        if not (own or ingress):
            raise ImproperlyConfigured(
                "Client accepts only owned signing identities or Commercial client-only ingress"
            )
