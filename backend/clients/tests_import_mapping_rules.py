from datetime import date
from unittest import TestCase

from clients.import_mapping import physical_source, nonempty_contact_updates, physical_account_holder


class ImportMappingRulesTests(TestCase):
    def test_physical_positions_and_normalized_date(self):
        row = physical_source({'2': 'P-001', '29': 'OTHER', '3': 'Exemple',
                               '4': 'Nadia', '9': '02/01/2000', '15': 'n@example.test'},
                              {'9': '2000-01-02'})
        self.assertEqual((row.source_id, row.first_name, row.last_name), ('P-001', 'Nadia', 'Exemple'))
        self.assertEqual(row.birth_date, date(2000, 1, 2))
        self.assertEqual(nonempty_contact_updates(row), {'email': 'n@example.test'})

    def test_blank_email_does_not_erase_existing_value(self):
        row = physical_source({'2': 'P-001', '15': '   '}, {})
        self.assertEqual(nonempty_contact_updates(row), {})

    def test_excel_datetime_birth_date_is_normalized_to_civil_date(self):
        row = physical_source({'2': 'P-001'}, {'9': '1992-05-14T00:00:00'})
        self.assertEqual(row.birth_date, date(1992, 5, 14))

    def test_source_key_never_falls_back_to_second_identifier(self):
        with self.assertRaises(ValueError):
            physical_source({'29': 'P-001'}, {})
        with self.assertRaises(ValueError):
            physical_source({'2': ' P-001'}, {})

    def test_phone_uses_telephone_then_mobile(self):
        row = physical_source({'2': 'P-001', '12': '111', '13': '222'}, {})
        self.assertEqual(nonempty_contact_updates(row), {'phone': '111'})
        row = physical_source({'2': 'P-001', '13': '222'}, {})
        self.assertEqual(nonempty_contact_updates(row), {'phone': '222'})

    def test_account_holder_uses_column_d(self):
        self.assertEqual(physical_account_holder({'4': 'P-001', '5': 'ACCOUNT-001'}), 'P-001')
        with self.assertRaises(ValueError):
            physical_account_holder({'5': 'ACCOUNT-001'})
