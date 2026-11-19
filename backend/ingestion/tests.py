from io import BytesIO
from datetime import date
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import transaction, DatabaseError, connection, connections
from concurrent.futures import ThreadPoolExecutor
from rest_framework.exceptions import ValidationError, PermissionDenied
from testing import fixtures
from identity.models import RoleAssignment
from clients.models import Party, FinancialAccount
from .models import ImportBatch, ImportPolicy, SourceSnapshot, StagingRow
from .templates import TEMPLATES
from .parser import parse
from .services import stage, create_policy, approve_policy, publish, publish_fixed
import openpyxl


def workbook(template="legal", ids=("SYNTH-001",), mutate=None):
    spec = TEMPLATES[template]
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = spec["sheet"]
    sheet.append(spec["headers"])
    for key in ids:
        row = [None] * len(spec["headers"])
        row[spec["candidate_keys"][0] - 1] = key
        if template == "legal":
            row[3] = "SOCIÉTÉ SYNTHÉTIQUE"
        if template == "physical":
            row[2] = "Synthétique"
            row[3] = "Exemple"
        sheet.append(row)
    if mutate:
        mutate(sheet)
    out = BytesIO()
    book.save(out)
    return out.getvalue()


class ImportTests(TestCase):
    def test_fixed_publication_detects_all_types_and_preserves_audit(self):
        from audit.models import AuditEvent
        for template, position in (("physical", 2), ("legal", 2), ("accounts", 5)):
            with self.subTest(template=template):
                batch, created = stage(self.reader, self.org_a.pk, None, date(2026, 1, 1),
                                       "partial", workbook(template=template), data_scope="synthetic")
                self.assertTrue(created)
                self.assertEqual(batch.template, template)
                with self.assertRaises(PermissionDenied):
                    publish_fixed(self.reader, self.org_a.pk, batch.pk)
                publish_fixed(self.manager, self.org_a.pk, batch.pk)
                batch.refresh_from_db()
                self.assertEqual(batch.fixed_configuration_version, 1)
                self.assertIsNone(batch.policy_id)
                self.assertEqual(batch.rows.first().sourcesnapshot.external_key,
                                 batch.rows.first().cells[str(position)])
                event = AuditEvent.objects.filter(action="imports.published", target_id=batch.pk).first()
                self.assertIsNotNone(event)
                self.assertEqual(event.context["key_column"], position)

    def test_legacy_publication_requires_one_approved_compatible_rule(self):
        batch = self.staged()
        with self.assertRaises(ValidationError):
            publish_fixed(self.manager, self.org_a.pk, batch.pk)
        rule = self.policy()
        publish_fixed(self.manager, self.org_a.pk, batch.pk)
        batch.refresh_from_db()
        self.assertEqual(batch.policy_id, rule.pk)
        self.assertIsNone(batch.fixed_configuration_version)

    def test_ambiguous_legacy_rules_require_reclassification(self):
        batch = self.staged()
        self.policy()
        second = create_policy(self.reader, self.org_a.pk, "legal", 2,
                               "Second historical synthetic rule with separate provenance")
        approve_policy(self.manager, self.org_a.pk, second.pk)
        with self.assertRaises(ValidationError):
            publish_fixed(self.manager, self.org_a.pk, batch.pk)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "staged")

    def test_fixed_publication_api_rejects_rule_modification_and_substitution(self):
        batch = self.scoped_batch()
        root = f"/api/imports/{self.org_a.pk}/"
        self.login_as(self.reader)
        self.assertEqual(self.client.post(root + "policies/", {}, content_type="application/json").status_code, 405)
        self.login_as(self.manager)
        self.assertEqual(self.client.post(root + f"batches/{batch.pk}/publish/",
                                          {"policy_id": str(batch.pk)}, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(root + f"batches/{batch.pk}/publish/",
                                          {}, content_type="application/json").status_code, 200)

    def test_review_diagnostics_distinguish_pending_revoked_and_date_mismatch(self):
        from .matching import policy_match
        from .views import PolicyOutput
        rule = self.scoped_rule()
        batch = self.scoped_batch()
        self.assertEqual(policy_match(batch, PolicyOutput)["detail_code"], "pending")
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        dated = stage(self.reader, self.org_a.pk, "legal", date(2026, 1, 1), "partial", workbook(), date_format="DMY", data_scope="synthetic")[0]
        self.assertEqual(policy_match(dated, PolicyOutput)["detail_code"], "date_format")
        approve_policy(self.manager, self.org_a.pk, rule.pk, revoke=True)
        self.assertEqual(policy_match(batch, PolicyOutput)["detail_code"], "revoked")

    def test_published_key_warning_does_not_cross_usage_boundaries(self):
        rule = self.scoped_rule()
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        original = self.scoped_batch()
        publish(self.manager, self.org_a.pk, original.pk, rule.pk)
        other = self.scoped_batch(scope="operational")
        self.assertEqual(other.rows.first().warnings, [])

    def test_matching_validates_approved_key_and_explicit_date_format(self):
        from .matching import policy_match
        from .views import PolicyOutput
        rule = create_policy(self.reader, self.org_a.pk, "physical", 29, "Synthetic alternate approved column, no identity mapping", data_scope="synthetic")
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        batch = stage(self.reader, self.org_a.pk, "physical", date(2026, 1, 1), "partial", workbook(template="physical"), data_scope="synthetic")[0]
        self.assertEqual(policy_match(batch, PolicyOutput)["status"], "invalid_key")
        legal = self.scoped_rule()
        approve_policy(self.manager, self.org_a.pk, legal.pk)
        dated = stage(self.reader, self.org_a.pk, "legal", date(2026, 1, 1), "partial", workbook(), date_format="DMY", data_scope="synthetic")[0]
        self.assertEqual(policy_match(dated, PolicyOutput)["status"], "missing")
        rejected = stage(self.reader, self.org_a.pk, "legal", date(2026, 1, 1), "partial", workbook(ids=("SYNTH-DUP", "SYNTH-DUP")), data_scope="synthetic")[0]
        self.assertEqual(policy_match(rejected, PolicyOutput)["status"], "invalid_rows")

    def test_matching_is_independent_of_rule_list_pagination_and_revoked_grants(self):
        from .matching import policy_match
        from .views import PolicyOutput
        rule = self.scoped_rule()
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        for index in range(101):
            self.scoped_rule(rationale=f"Synthetic distinct pending policy text {index}")
        batch = self.scoped_batch()
        self.assertEqual(policy_match(batch, PolicyOutput)["policy"]["id"], str(rule.pk))
        self.login_as(self.reader)
        first = self.client.get(f"/api/imports/{self.org_a.pk}/policies/?view=available")
        second = self.client.get(f"/api/imports/{self.org_a.pk}/policies/?view=available&page=2")
        self.assertEqual(len(first.data), 100)
        self.assertIn(str(rule.pk), [row["id"] for row in second.data])
        RoleAssignment.objects.filter(membership=self.reader_m).delete()
        self.assertEqual(self.client.get(f"/api/imports/{self.org_a.pk}/batches/{batch.pk}/").status_code, 403)

    def scoped_rule(self, scope="synthetic", rationale="Synthetic reusable rule: immutable snapshots only"):
        return create_policy(self.reader, self.org_a.pk, "legal", 2, rationale, data_scope=scope)

    def scoped_batch(self, scope="synthetic", key="SYNTH-REUSE"):
        return stage(self.reader, self.org_a.pk, "legal", date(2026, 1, 1), "partial", workbook(ids=(key,)), data_scope=scope)[0]

    def test_identical_proposal_reuses_version_without_new_audit(self):
        from audit.models import AuditEvent
        rule = self.scoped_rule()
        count = AuditEvent.objects.filter(action="imports.policy_created").count()
        self.assertEqual(self.scoped_rule().pk, rule.pk)
        self.assertEqual(AuditEvent.objects.filter(action="imports.policy_created").count(), count)
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        self.assertEqual(self.scoped_rule().pk, rule.pk)

    def test_one_active_rule_and_explicit_replacement_retains_history(self):
        rule = self.scoped_rule()
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        batch = self.scoped_batch()
        publish(self.manager, self.org_a.pk, batch.pk, rule.pk)
        replacement = self.scoped_rule(rationale="Changed synthetic publication policy requiring new approval")
        with self.assertRaises(ValidationError):
            approve_policy(self.manager, self.org_a.pk, replacement.pk)
        approve_policy(self.manager, self.org_a.pk, rule.pk, revoke=True)
        approve_policy(self.manager, self.org_a.pk, replacement.pk)
        batch.refresh_from_db()
        self.assertEqual(batch.policy_id, rule.pk)
        self.assertEqual(batch.rows.filter(sourcesnapshot__isnull=False).count(), 1)

    def test_suggestion_reused_but_every_batch_requires_independent_review(self):
        from .matching import policy_match
        from .views import PolicyOutput
        rule = self.scoped_rule()
        batch = self.scoped_batch()
        self.assertEqual(policy_match(batch, PolicyOutput)["status"], "missing")
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        for current in [batch, self.scoped_batch(key="SYNTH-SECOND")]:
            self.assertEqual(policy_match(current, PolicyOutput)["policy"]["id"], str(rule.pk))
            with self.assertRaises(PermissionDenied):
                publish(self.reader, self.org_a.pk, current.pk, rule.pk)
            publish(self.manager, self.org_a.pk, current.pk, rule.pk)
        approve_policy(self.manager, self.org_a.pk, rule.pk, revoke=True)
        self.assertEqual(policy_match(self.scoped_batch(key="SYNTH-THIRD"), PolicyOutput)["status"], "missing")

    def test_usage_and_schema_are_not_interchangeable(self):
        from .matching import policy_match
        from .views import PolicyOutput
        rule = self.scoped_rule()
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        batch = self.scoped_batch(scope="operational")
        self.assertEqual(policy_match(batch, PolicyOutput)["status"], "missing")
        with self.assertRaises(ValidationError):
            publish(self.manager, self.org_a.pk, batch.pk, rule.pk)
        with self.assertRaises(ValidationError):
            create_policy(self.reader, self.org_a.pk, "legal", 2, "Synthetic unsupported schema approval", template_version=999)
        self.assertEqual(policy_match(self.staged(), PolicyOutput)["status"], "unclassified")

    def test_rule_configuration_and_import_classification_immutable_in_database(self):
        rule = self.scoped_rule()
        batch = self.scoped_batch()
        for mutation in [lambda: ImportPolicy.objects.filter(pk=rule.pk).update(key_column=1), lambda: ImportPolicy.objects.filter(pk=rule.pk).update(rationale="changed"), lambda: ImportBatch.objects.filter(pk=batch.pk).update(data_scope="operational")]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                mutation()

    def test_suggestion_requires_authorized_organization_and_approved_valid_rows(self):
        rule = self.scoped_rule()
        approve_policy(self.manager, self.org_a.pk, rule.pk)
        batch = self.scoped_batch()
        self.login_as(self.it)
        self.assertEqual(self.client.get(f"/api/imports/{self.org_a.pk}/batches/{batch.pk}/").status_code, 403)
        self.login_as(self.reader)
        response = self.client.get(f"/api/imports/{self.org_a.pk}/batches/{batch.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["policy_match"]["policy"]["id"], str(rule.pk))

    def setUp(self):
        fixtures.SecurityFixtures.setUp(self)
        self.default_workbook = workbook()

    login_as = fixtures.SecurityFixtures.login_as

    @classmethod
    def setUpTestData(cls):
        fixtures.SecurityFixtures.setUpTestData.__func__(cls)
        upload = fixtures.role(
            "import-upload",
            [
                "imports.view",
                "imports.upload",
                "imports.policy_manage",
                "clients.view_financial",
            ],
        )
        approve = fixtures.role(
            "import-review",
            ["imports.view", "imports.approve", "clients.view_financial"],
        )
        RoleAssignment.objects.create(
            membership=cls.reader_m, role=upload, scope="organization"
        )
        RoleAssignment.objects.create(
            membership=cls.manager_m, role=approve, scope="organization"
        )

    def staged(self, content=None):
        return stage(
            self.reader,
            self.org_a.pk,
            "legal",
            date(2026, 1, 1),
            "partial",
            self.default_workbook if content is None else content,
        )[0]

    def policy(self):
        policy = create_policy(
            self.reader,
            self.org_a.pk,
            "legal",
            2,
            "Synthetic explicit key rule; immutable snapshots only",
        )
        approve_policy(self.manager, self.org_a.pk, policy.pk)
        return policy

    def test_templates_actual_columns_and_positional_duplicate_header(self):
        self.assertEqual(
            [
                len(TEMPLATES[key]["headers"])
                for key in ["physical", "legal", "accounts"]
            ],
            [33, 25, 41],
        )
        self.assertEqual(
            TEMPLATES["physical"]["headers"][1], TEMPLATES["physical"]["headers"][28]
        )
        for template in TEMPLATES:
            self.assertFalse(parse(workbook(template), template)[0]["errors"])

    def test_date_format_is_explicit_preserves_raw_values_and_requires_matching_rule(
        self,
    ):
        raw = workbook(
            "accounts",
            mutate=lambda sheet: (
                setattr(sheet["I2"], "value", "13/02/2026"),
                setattr(sheet["N2"], "value", "synthetic.operator"),
            ),
        )
        self.assertTrue(parse(raw, "accounts")[0]["errors"])
        row = parse(raw, "accounts", "DMY")[0]
        self.assertFalse(row["errors"])
        self.assertEqual(row["cells"]["9"], "13/02/2026")
        self.assertEqual(row["normalized_dates"]["9"], "2026-02-13")
        batch = stage(
            self.reader,
            self.org_a.pk,
            "accounts",
            date(2026, 2, 13),
            "partial",
            raw,
            date_format="DMY",
        )[0]
        wrong = create_policy(
            self.reader,
            self.org_a.pk,
            "accounts",
            5,
            "Synthetic wrong date interpretation policy",
        )
        approve_policy(self.manager, self.org_a.pk, wrong.pk)
        with self.assertRaises(ValidationError):
            publish(self.manager, self.org_a.pk, batch.pk, wrong.pk)
        correct = create_policy(
            self.reader,
            self.org_a.pk,
            "accounts",
            5,
            "Synthetic explicit day month year snapshot policy",
            date_format="DMY",
        )
        approve_policy(self.manager, self.org_a.pk, correct.pk)
        publish(self.manager, self.org_a.pk, batch.pk, correct.pk)
        self.assertEqual(SourceSnapshot.objects.count(), 1)
        inconsistent = stage(
            self.reader,
            self.org_a.pk,
            "accounts",
            date(2026, 2, 12),
            "partial",
            raw,
            date_format="DMY",
        )[0]
        self.assertTrue(inconsistent.rows.first().errors)
        with self.assertRaises(ValidationError):
            publish(self.manager, self.org_a.pk, inconsistent.pk, correct.pk)

    def test_malformed_header_formulas_dates_ids_and_duplicates(self):
        for content in [
            b"not xlsx",
            b"",
            workbook(mutate=lambda s: setattr(s["B1"], "value", "Wrong header")),
        ]:
            with self.assertRaises(ValidationError):
                parse(content, "legal")
        rows = parse(
            workbook(
                ids=("DUP", "DUP", 123, "VALID"),
                mutate=lambda s: setattr(
                    s["C5"], "value", '=HYPERLINK("https://invalid")'
                ),
            ),
            "legal",
        )
        self.assertTrue(all(row["errors"] for row in rows))
        data = workbook(
            "physical", mutate=lambda s: setattr(s["I2"], "value", "01/02/03")
        )
        self.assertTrue(parse(data, "physical")[0]["errors"])

    def test_zip_threats_and_extra_sheets(self):
        for name, value in [
            ("../evil.xml", b"<x/>"),
            ("xl/externalLinks/x.xml", b"<x/>"),
            ("x.xml", b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>'),
            ("xl/vbaProject.bin", b"x"),
            ("x.bin", b"0" * 100000),
        ]:
            out = BytesIO()
            with ZipFile(out, "w", ZIP_DEFLATED) as z:
                z.writestr(name, value)
            with self.assertRaises(ValidationError):
                parse(out.getvalue(), "legal")
        with self.assertRaises(ValidationError):
            parse(workbook(mutate=lambda s: s.parent.create_sheet("Hidden")), "legal")

    def test_publication_policy_separation_idempotence_and_no_domain_overwrite(self):
        before = (Party.objects.count(), FinancialAccount.objects.count())
        batch = self.staged()
        policy = self.policy()
        self.assertEqual(self.staged().pk, batch.pk)
        with self.assertRaises(PermissionDenied):
            publish(self.reader, self.org_a.pk, batch.pk, policy.pk)
        publish(self.manager, self.org_a.pk, batch.pk, policy.pk)
        publish(self.manager, self.org_a.pk, batch.pk, policy.pk)
        self.assertEqual(SourceSnapshot.objects.count(), 1)
        self.assertEqual(
            before, (Party.objects.count(), FinancialAccount.objects.count())
        )
        with self.assertRaises(PermissionDenied):
            approve_policy(self.reader, self.org_a.pk, policy.pk)

    def test_rejected_rows_atomic_publication_and_audit_failure(self):
        batch = self.staged(workbook(ids=("VALID", "DUP", "DUP")))
        policy = self.policy()
        with self.assertRaises(ValidationError):
            publish(self.manager, self.org_a.pk, batch.pk, policy.pk)
        with patch(
            "ingestion.services.record",
            side_effect=RuntimeError("Synthetic audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                publish(self.manager, self.org_a.pk, batch.pk, policy.pk, True)
        self.assertEqual(SourceSnapshot.objects.count(), 0)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "staged")
        publish(self.manager, self.org_a.pk, batch.pk, policy.pk, True)
        self.assertEqual(SourceSnapshot.objects.count(), 1)
        self.assertEqual(batch.rows.exclude(errors=[]).count(), 2)

    def test_unapproved_revoked_wrong_org_and_insufficient_permissions(self):
        batch = self.staged()
        policy = create_policy(
            self.reader,
            self.org_a.pk,
            "legal",
            2,
            "Synthetic pending rule approval explanation",
        )
        with self.assertRaises(ValidationError):
            publish(self.manager, self.org_a.pk, batch.pk, policy.pk)
        approve_policy(self.manager, self.org_a.pk, policy.pk)
        approve_policy(self.manager, self.org_a.pk, policy.pk, revoke=True)
        with self.assertRaises(ValidationError):
            publish(self.manager, self.org_a.pk, batch.pk, policy.pk)
        self.login_as(self.it)
        for tail in [
            "batches/",
            f"batches/{batch.pk}/",
            f"batches/{batch.pk}/rejections/",
            "policies/",
        ]:
            self.assertEqual(
                self.client.get(f"/api/imports/{self.org_a.pk}/{tail}").status_code, 403
            )
        self.login_as(self.reader)
        self.assertEqual(
            self.client.get(
                f"/api/imports/{self.org_b.pk}/batches/{batch.pk}/"
            ).status_code,
            403,
        )

    def test_cross_batch_duplicate_warning_is_scoped_and_history_is_preserved(self):
        original = self.staged()
        policy = self.policy()
        publish(self.manager, self.org_a.pk, original.pk, policy.pk)
        changed = workbook(
            mutate=lambda sheet: setattr(
                sheet["D2"], "value", "SYNTHETIC CHANGED SOURCE LABEL"
            )
        )
        new_batch = self.staged(changed)
        self.assertTrue(new_batch.rows.first().warnings)
        publish(self.manager, self.org_a.pk, new_batch.pk, policy.pk)
        self.assertEqual(SourceSnapshot.objects.count(), 2)
        self.assertEqual(original.rows.first().cells["4"], "SOCIÉTÉ SYNTHÉTIQUE")

    def test_imports_capability_does_not_bypass_financial_scope_or_object_scope(self):
        from identity.models import Membership

        imports_only = fixtures.role(
            "synthetic-imports-only",
            ["imports.view", "imports.upload", "imports.approve"],
        )
        RoleAssignment.objects.create(
            membership=self.it_m, role=imports_only, scope="organization"
        )
        self.login_as(self.it)
        self.assertEqual(
            self.client.get(f"/api/imports/{self.org_a.pk}/batches/").status_code, 403
        )
        finance = fixtures.role(
            "synthetic-finance-other-org", ["clients.view_financial"]
        )
        member = Membership.objects.create(user=self.it, organization=self.org_b)
        RoleAssignment.objects.create(
            membership=member, role=finance, scope="organization"
        )
        self.assertEqual(
            self.client.get("/api/imports/context/").json()["organizations"], []
        )
        # A reader with org A import authority cannot substitute an org B batch ID.
        foreign = ImportBatch.objects.create(
            organization=self.org_b,
            template="legal",
            digest="f" * 64,
            source_as_of=date(2026, 1, 1),
            uploaded_by=self.other,
        )
        self.login_as(self.reader)
        self.assertEqual(
            self.client.get(
                f"/api/imports/{self.org_a.pk}/batches/{foreign.pk}/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/imports/{self.org_a.pk}/batches/{foreign.pk}/rejections/"
            ).status_code,
            404,
        )

    def test_upload_preview_reports_and_csrf(self):
        self.login_as(self.reader)
        url = f"/api/imports/{self.org_a.pk}/upload/?template=legal&source_as_of=2026-01-01"
        content = workbook(
            ids=("VALID", "DUP", "DUP"),
            mutate=lambda s: setattr(s["C3"], "value", "+SUM(1,2)"),
        )
        response = self.client.post(
            url, content, content_type="application/octet-stream"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            self.client.post(
                url, content, content_type="application/octet-stream"
            ).status_code,
            200,
        )
        base = f'/api/imports/{self.org_a.pk}/batches/{response.data["id"]}/'
        preview = self.client.get(base).json()
        self.assertEqual(preview["count"], 3)
        self.assertEqual(preview["batch"]["rejected"], 2)
        report = self.client.get(base + "rejections/")
        self.assertEqual(report.status_code, 200)
        self.assertIn("'+SUM", report.content.decode("utf-8"))
        with patch("ingestion.views.MAX_BYTES", 100):
            self.assertEqual(
                self.client.post(
                    url, content, content_type="application/octet-stream"
                ).status_code,
                413,
            )
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                url, content, content_type="application/octet-stream"
            ).status_code,
            403,
        )

    def test_source_rows_immutable_postgres(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        batch = self.staged()
        with self.assertRaises(DatabaseError), transaction.atomic():
            batch.rows.update(cells={})
        policy=self.policy()
        publish(self.manager,self.org_a.pk,batch.pk,policy.pk)
        with self.assertRaises(DatabaseError),transaction.atomic():
            SourceSnapshot.objects.update(external_key='Forbidden mutation')

    def test_database_rejects_inconsistent_publication_and_approval_state(self):
        from django.utils import timezone
        batch=self.staged()
        with self.assertRaises(DatabaseError),transaction.atomic():
            ImportBatch.objects.filter(pk=batch.pk).update(status='published')
        policy=create_policy(self.reader,self.org_a.pk,'legal',2,'Synthetic pending policy database consistency')
        with self.assertRaises(DatabaseError),transaction.atomic():
            ImportPolicy.objects.filter(pk=policy.pk).update(approved_at=timezone.now())

    @override_settings(IMPORT_MAX_STAGED_BATCHES=1)
    def test_staging_quota_does_not_break_idempotent_replay(self):
        from rest_framework.exceptions import Throttled

        batch = self.staged()
        self.assertEqual(self.staged().pk, batch.pk)
        with self.assertRaises(Throttled):
            self.staged(workbook(ids=("NEW-SYNTHETIC-KEY",)))


class ImportConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL concurrency")
        with transaction.atomic():
            fixtures.SecurityFixtures.setUpTestData.__func__(type(self))
        capabilities = [
            "imports.view",
            "imports.upload",
            "imports.approve",
            "imports.policy_manage",
            "clients.view_financial",
        ]
        grant = fixtures.role("synthetic-concurrent-import", capabilities)
        RoleAssignment.objects.create(
            membership=self.reader_m, role=grant, scope="organization"
        )
        RoleAssignment.objects.create(
            membership=self.manager_m, role=grant, scope="organization"
        )

    def test_concurrent_staging_and_publication_have_one_effect(self):
        content = workbook()

        def upload():
            try:
                return stage(
                    self.reader,
                    self.org_a.pk,
                    "legal",
                    date(2026, 1, 1),
                    "partial",
                    content,
                )[0].pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = list(pool.map(lambda _: upload(), range(2)))
        self.assertEqual(batches[0], batches[1])
        self.assertEqual(ImportBatch.objects.count(), 1)
        policy = create_policy(
            self.reader,
            self.org_a.pk,
            "legal",
            2,
            "Synthetic concurrent approved snapshot rule",
        )
        approve_policy(self.manager, self.org_a.pk, policy.pk)

        def publication():
            try:
                return publish(self.manager, self.org_a.pk, batches[0], policy.pk).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: publication(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(SourceSnapshot.objects.count(), 1)
