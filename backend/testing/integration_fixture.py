"""Synthetic S3 actors/history in a marked restored database only."""

import json
import os
from datetime import date
from pathlib import Path
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection, transaction
from identity.models import User, Organization, Membership, RoleAssignment
from testing.fixtures import role
from testing.rehearsal import validate_environment
from ingestion.tests import workbook
from ingestion.services import stage, create_policy, approve_policy, publish


def main():
    validate_environment(os.environ)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
        )
        if cursor.fetchone()[0] != "aiced-m1:" + os.environ["AICED_REHEARSAL_RUN"]:
            raise ValueError("Scratch ownership marker required")
    run = os.environ["AICED_REHEARSAL_RUN"][:12]
    state = {}
    with transaction.atomic():
        org = Organization.objects.create(
            code="S3-" + run, name="S3 organisation synthétique"
        )
        other = Organization.objects.create(
            code="S3-X-" + run, name="S3 autre organisation synthétique"
        )
        for name, codes in (
            (
                "uploader",
                [
                    "imports.view",
                    "imports.upload",
                    "imports.policy_manage",
                    "clients.view_financial",
                ],
            ),
            (
                "reviewer",
                [
                    "imports.view",
                    "imports.approve",
                    "clients.view_financial",
                    "audit.view",
                ],
            ),
            (
                "it",
                [
                    "imports.view",
                    "imports.upload",
                    "imports.approve",
                    "imports.policy_manage",
                ],
            ),
        ):
            user = User.objects.create_user(
                f"s3.{run}.{name}",
                password=os.environ["AICED_S3_PASSWORD"],
                is_superuser=name == "it",
                is_staff=name == "it",
            )
            membership = Membership.objects.create(user=user, organization=org)
            grant = RoleAssignment.objects.create(
                membership=membership,
                role=role("s3-" + run + name, codes),
                scope="organization",
            )
            state[name] = {
                "id": str(user.pk),
                "username": user.username,
                "assignment_id": str(grant.pk),
            }
        uploader = User.objects.get(pk=state["uploader"]["id"])
        reviewer = User.objects.get(pk=state["reviewer"]["id"])
        policy = create_policy(
            uploader,
            org.pk,
            "legal",
            2,
            "SYNTHETIC ONLY reviewed immutable source snapshots",
        )
        approve_policy(reviewer, org.pk, policy.pk)
        batch, _ = stage(
            uploader,
            org.pk,
            "legal",
            date.today(),
            "partial",
            workbook(ids=("S3-HISTORY-" + run,)),
        )
        publish(reviewer, org.pk, batch.pk, policy.pk)
        state.update(
            organization_id=str(org.pk),
            other_organization_id=str(other.pk),
            policy_id=str(policy.pk),
            batch_id=str(batch.pk),
        )
    Path(os.environ["AICED_S3_STATE"]).write_text(json.dumps(state))
    print("Synthetic S3 identities and published history prepared")


if __name__ == "__main__":
    main()
