from io import BytesIO
from django.test import SimpleTestCase
from openpyxl import Workbook
from rest_framework.exceptions import ValidationError

from .parser import parse
from .templates import FIXED_CONFIGURATIONS, TEMPLATES
from .views import PoliciesView, PolicyApproveView, PublishInput


def workbook(template, key, other=None):
    spec = TEMPLATES[template]
    book = Workbook()
    sheet = book.active
    sheet.title = spec["sheet"]
    sheet.append(spec["headers"])
    row = [None] * len(spec["headers"])
    row[FIXED_CONFIGURATIONS[template]["key_column"] - 1] = key
    if template == "physical":
        row[28] = other
    sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


class FixedConfigurationParserTests(SimpleTestCase):
    def test_three_workbooks_use_fixed_keys(self):
        self.assertEqual({k: v["key_column"] for k, v in FIXED_CONFIGURATIONS.items()},
                         {"physical": 2, "legal": 2, "accounts": 5})
        for template in FIXED_CONFIGURATIONS:
            with self.subTest(template=template):
                rows = parse(workbook(template, "SYNTH-001"), template)
                self.assertEqual(rows[0]["errors"], [])

    def test_physical_ac_does_not_replace_missing_b(self):
        rows = parse(workbook("physical", None, "SYNTH-AC"), "physical")
        self.assertTrue(rows[0]["errors"])

    def test_wrong_template_is_rejected(self):
        with self.assertRaises(ValidationError):
            parse(workbook("physical", "SYNTH-001"), "legal")

    def test_public_rule_modification_and_substitution_are_disabled(self):
        self.assertFalse(hasattr(PoliciesView, "post"))
        from rest_framework.exceptions import MethodNotAllowed
        with self.assertRaises(MethodNotAllowed):
            PolicyApproveView().post(None, "organization", "policy")
        serializer = PublishInput(data={"policy_id": "00000000-0000-0000-0000-000000000001"})
        self.assertFalse(serializer.is_valid())

    def test_date_format_and_rejected_rows_are_preserved(self):
        book = Workbook()
        sheet = book.active
        sheet.title = TEMPLATES["physical"]["sheet"]
        sheet.append(TEMPLATES["physical"]["headers"])
        row = [None] * len(TEMPLATES["physical"]["headers"])
        row[1] = "SYNTH-DATE"
        row[8] = "13/02/2000"
        sheet.append(row)
        output = BytesIO()
        book.save(output)
        self.assertEqual(parse(output.getvalue(), "physical", "DMY")[0]["normalized_dates"]["9"], "2000-02-13")
        self.assertTrue(parse(output.getvalue(), "physical", "ISO")[0]["errors"])
