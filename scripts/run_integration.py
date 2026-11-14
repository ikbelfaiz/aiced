"""Run the isolated service with a private JSON environment (no IAM DB secret)."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    env = {**os.environ, **json.loads(options.env_file.read_text())}
    env["PYTHONPATH"] = str(ROOT / ".tools/python")
    return subprocess.call(
        [
            sys.executable,
            str(ROOT / "backend/integration_service/manage.py"),
            *(options.command or ["runserver", "127.0.0.1:8002", "--noreload"]),
        ],
        cwd=ROOT,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
