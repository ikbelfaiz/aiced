"""Synthetic restore fixture, inaccessible to the normal application database."""

import json
import os
from datetime import date
from io import BytesIO
from pathlib import Path
import openpyxl
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.contrib.sessions.backends.db import SessionStore
from rest_framework.test import APIClient
from testing.rehearsal import validate_environment


class Command(BaseCommand):
    help = "Prepare or verify only this run's new synthetic scratch database."

    def add_arguments(self, parser):
        parser.add_argument("--state-file", required=True)
        parser.add_argument("--verify", action="store_true")

    def handle(self, *args, **options):
        try:
            validate_environment(os.environ, settings.DATABASES["default"]["NAME"])
        except ValueError as exc:
            raise CommandError(str(exc))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
            )
            if cursor.fetchone()[0] != "aiced-m1:" + os.environ["AICED_REHEARSAL_RUN"]:
                raise CommandError("Scratch database ownership marker missing.")
        state_file = Path(options["state_file"])
        if options["verify"]:
            state = json.loads(state_file.read_text())
            client = APIClient()
            client.cookies[settings.SESSION_COOKIE_NAME] = state["session_key"]
            response = client.get("/api/session/")
            if (
                response.status_code != 200
                or response.data["username"] != "synthetic.operator.a"
            ):
                raise CommandError(
                    "Restored session or authentication hash is invalid."
                )
            response = client.get(f"/api/clients/{state['party_id']}/workspace/")
            if response.status_code != 200 or response.data["crm"]["version"] != 2:
                raise CommandError("Restored workspace/version not preserved.")
            response = client.get(
                f"/api/imports/{state['organization_id']}/batches/{state['batch_id']}/"
            )
            if (
                response.status_code != 200
                or response.data["batch"]["published_rows"] != 1
            ):
                raise CommandError("Restored publication history not preserved.")
            self.stdout.write(
                "Restored session, workspace version and published import verified."
            )
            return
        if not settings.DATABASES["default"]["NAME"].endswith("_source"):
            raise CommandError(
                "Fixture creation is permitted only on the new source scratch database."
            )
        from identity.models import User, Organization
        from identity.authentication import consume_login_budget
        from clients.models import Party, ExternalIdentity
        from clients.workspace import edit_profile, save_activity
        from ingestion.services import stage, create_policy, approve_policy, publish
        from ingestion.templates import TEMPLATES
        from audit.services import record

        for name in ["seed_synthetic", "seed_workspace", "seed_prospects"]:
            call_command(name, confirm_synthetic=True, stdout=self.stdout)
        operator = User.objects.get(username="synthetic.operator.a")
        reviewer = User.objects.get(username="synthetic.reviewer.a")
        org = Organization.objects.get(code="SYNTHETIC-A")
        party = Party.objects.get(organization=org, origin="SYNTHETIC_ONLY")
        ExternalIdentity.objects.create(
            party=party, source="SYNTHETIC_ONLY", external_id="SYNTHETIC-RESTORE-PARTY"
        )
        edit_profile(
            operator, party.pk, {"version": 1, "notes": "SYNTHETIC restoration fixture"}
        )
        save_activity(
            operator,
            party.pk,
            "interactions",
            {
                "kind": "call",
                "subject": "SYNTHETIC restoration call",
                "occurred_at": "2026-01-01T10:00:00Z",
            },
        )
        save_activity(
            operator,
            party.pk,
            "opportunities",
            {"title": "SYNTHETIC restoration estimate", "amount": "123.456"},
        )
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Tier"
        sheet.append(TEMPLATES["legal"]["headers"])
        for key in ["SYNTHETIC-RESTORE", "SYNTHETIC-DUP", "SYNTHETIC-DUP"]:
            row = [None] * 25
            row[1] = key
            row[3] = "SYNTHETIC restoration company"
            sheet.append(row)
        content = BytesIO()
        book.save(content)
        batch, _ = stage(
            operator, org.pk, "legal", date(2026, 1, 1), "partial", content.getvalue()
        )
        policy = create_policy(
            operator,
            org.pk,
            "legal",
            2,
            "SYNTHETIC immutable snapshot restoration policy",
        )
        approve_policy(reviewer, org.pk, policy.pk)
        publish(reviewer, org.pk, batch.pk, policy.pk, skip_rejected=True)
        consume_login_budget("synthetic.restore", "192.0.2.1")
        session = SessionStore()
        session["_auth_user_id"] = str(operator.pk)
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["_auth_user_hash"] = operator.get_session_auth_hash()
        session.save()
        record(
            "migration.synthetic_fixture",
            actor=operator,
            organization_id=org.pk,
            target_id=party.pk,
        )
        state_file.write_text(
            json.dumps(
                {
                    "session_key": session.session_key,
                    "party_id": str(party.pk),
                    "organization_id": str(org.pk),
                    "batch_id": str(batch.pk),
                }
            )
        )
        self.stdout.write(
            "Synthetic restore fixture prepared; credentials were not printed."
        )
