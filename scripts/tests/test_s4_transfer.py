import sys
from pathlib import Path
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s4_transfer import transfer, activate, frozen


class CutoverSafetyTests(unittest.TestCase):
    def test_unknown_schema_pair_is_refused_before_sql(self):
        conn = Mock()
        for source, destination in [
            ("public", "public"),
            ("public", "other_service"),
            ("aiced_integration", "identity"),
        ]:
            with self.assertRaises(ValueError):
                transfer(conn, source, destination)
        conn.execute.assert_not_called()

    def test_unknown_route_owner_is_refused_before_sql(self):
        conn = Mock()
        with self.assertRaises(ValueError):
            activate(conn, "other_service")
        conn.execute.assert_not_called()

    def test_copy_requires_both_frozen_controls_and_offline_administrator(self):
        for responses in [
            [("legacy",)],
            [("frozen",), ("service",)],
            [("frozen",), ("frozen",), (False,)],
        ]:
            conn = Mock()
            conn.execute.return_value.fetchone.side_effect = responses
            with self.assertRaises(ValueError):
                frozen(conn)
            self.assertTrue(
                all(
                    "SELECT" in str(call.args[0])
                    for call in conn.execute.call_args_list
                )
            )
