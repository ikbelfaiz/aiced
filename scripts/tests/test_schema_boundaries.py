"""Safety guards before privileged, disposable schema rehearsal."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema_boundaries import guard


class ScratchSchemaGuards(unittest.TestCase):
    def env(self):
        return {
            "DJANGO_DEBUG": "1",
            "POSTGRES_HOST": "127.0.0.1",
            "AICED_REHEARSAL_RUN": "a" * 32,
            "POSTGRES_DB": "aiced_m1_" + ("a" * 32) + "_source",
        }

    def test_existing_application_database_cannot_be_provisioned(self):
        connection = Mock()
        with self.assertRaises(ValueError):
            guard(connection, {**self.env(), "POSTGRES_DB": "aiced"})
        connection.execute.assert_not_called()

    def test_missing_ownership_marker_refuses_all_mutations(self):
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = (
            self.env()["POSTGRES_DB"],
            None,
        )
        with self.assertRaises(ValueError):
            guard(connection, self.env())
        self.assertEqual(connection.execute.call_count, 1)

    def test_nonempty_database_refuses_provisioning(self):
        connection = Mock()
        connection.execute.return_value.fetchone.side_effect = [
            (self.env()["POSTGRES_DB"], "aiced-m1:" + "a" * 32),
            (1,),
        ]
        with self.assertRaises(ValueError):
            guard(connection, self.env())
        self.assertEqual(connection.execute.call_count, 2)
