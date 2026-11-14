import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from migration_baseline import (
    ScratchDatabases,
    canonical_constraint,
    require_equal,
    verify_restored_constraints,
)
from testing.rehearsal import validate_environment


class BaselineSafetyTests(unittest.TestCase):
    def setUp(self):
        self.run = "a" * 32
        self.name = f"aiced_m1_{self.run}_source"
        self.env = {
            "AICED_REHEARSAL_RUN": self.run,
            "DJANGO_DEBUG": "1",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_DB": self.name,
            "POSTGRES_USER": "synthetic",
            "POSTGRES_PASSWORD": "synthetic-test-only",
        }

    def test_only_generated_run_databases_are_accepted(self):
        self.assertEqual(validate_environment(self.env), self.name)
        for name in [
            "aiced",
            "postgres",
            f'aiced_m1_{"b"*32}_source',
            "test_" + self.name,
            self.name + ";DROP DATABASE aiced",
        ]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_environment(self.env, name)

    def test_non_debug_remote_or_missing_run_are_denied(self):
        for update in [
            {"DJANGO_DEBUG": "0"},
            {"POSTGRES_HOST": "db.example.invalid"},
            {"AICED_REHEARSAL_RUN": ""},
        ]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_environment({**self.env, **update})

    def test_existing_database_cannot_be_created_or_dropped(self):
        databases = ScratchDatabases(self.env, self.name)
        with patch("migration_baseline.psycopg.connect") as connect:
            for action in [databases.create, databases.drop]:
                with self.assertRaises(ValueError):
                    action(self.name)
            connect.assert_not_called()

    def test_cleanup_requires_process_ownership(self):
        databases = ScratchDatabases(self.env, "aiced")
        with patch("migration_baseline.psycopg.connect") as connect:
            with self.assertRaises(ValueError):
                databases.drop(self.name)
            connect.assert_not_called()

    def test_cleanup_refuses_changed_marker(self):
        databases = ScratchDatabases(self.env, "aiced")
        databases.created.append(self.name)
        with patch("migration_baseline.psycopg.connect") as connect:
            connection = connect.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = ("wrong-run",)
            with self.assertRaises(ValueError):
                databases.drop(self.name)
            self.assertEqual(connection.execute.call_count, 1)
            self.assertIn(self.name, databases.created)

    def test_constraint_probes_cannot_write_to_original_or_source(self):
        with patch("migration_baseline.psycopg.connect") as connect:
            for name in ["aiced", self.name]:
                with self.assertRaises(ValueError):
                    verify_restored_constraints({**self.env, "POSTGRES_DB": name})
            connect.assert_not_called()

    def test_data_schema_and_sequence_mismatches_fail_closed(self):
        baseline = {
            "tables": {"x": {"count": 1, "sha256": "a"}},
            "constraints": ["required"],
            "sequences": {"x": [3, True]},
        }
        for key in baseline:
            altered = {**baseline, key: {}}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                require_equal(baseline, altered, "Restore")

    def test_only_exact_equivalent_postgres_cast_forms_are_normalized(self):
        source = "CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'won'::character varying])::text[])))"
        restored = "CHECK (((status)::text = ANY (ARRAY[('open'::character varying)::text, ('won'::character varying)::text])))"
        self.assertEqual(canonical_constraint(source), canonical_constraint(restored))
        self.assertNotEqual(
            canonical_constraint(source),
            canonical_constraint(restored.replace("won", "lost")),
        )
        self.assertNotEqual(
            canonical_constraint(source), canonical_constraint("CHECK (true)")
        )
        self.assertNotEqual(
            canonical_constraint(source),
            canonical_constraint(restored[:-1] + " OR true)"),
        )


if __name__ == "__main__":
    unittest.main()
