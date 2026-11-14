import sys, unittest
from pathlib import Path

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1]),
    str(Path(__file__).resolve().parents[2] / ".tools/python"),
    str(Path(__file__).resolve().parents[2] / "backend"),
]
from s5_database import transfer, activate
from s5_local import validate


class S5SafetyTests(unittest.TestCase):
    def test_unknown_transfer_direction_rejected_before_sql(self):
        with self.assertRaises(ValueError):
            transfer(None, "other")

    def test_unknown_owner_rejected_before_sql(self):
        with self.assertRaises(ValueError):
            activate(None, "other")

    def test_remote_or_production_environment_refused(self):
        for env in [
            {},
            {
                "POSTGRES_DB": "aiced",
                "POSTGRES_HOST": "production",
                "POSTGRES_PORT": "55432",
                "DJANGO_DEBUG": "1",
            },
            {
                "POSTGRES_DB": "aiced",
                "POSTGRES_HOST": "127.0.0.1",
                "POSTGRES_PORT": "55432",
                "DJANGO_DEBUG": "0",
            },
        ]:
            with self.assertRaises(ValueError):
                validate(env)
