"""Start the S2 private contract listener against the existing local backend DB."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".local/postgres/env.json"
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        required=True,
        help="Private JSON key registry; never a command-line secret",
    )
    parser.add_argument("--port", type=int, default=8001)
    options = parser.parse_args()
    if not 1 <= options.port <= 65535:
        raise ValueError("Invalid private port")
    env = {**os.environ, **json.loads(options.env_file.read_text())}
    keys = json.loads(options.key_file.read_text())
    if env.get("DJANGO_DEBUG") != "1" or not keys:
        raise ValueError("Explicit local development configuration required")
    env["AICED_INTERNAL_KEYS"] = json.dumps(keys)
    env["PYTHONPATH"] = str(ROOT / ".tools/python")
    return subprocess.call(
        [
            sys.executable,
            str(ROOT / "backend/manage.py"),
            "runserver",
            f"127.0.0.1:{options.port}",
            "--noreload",
            "--settings",
            "internal_api.settings",
        ],
        env=env,
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
