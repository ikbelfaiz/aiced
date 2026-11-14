"""Run the M2 gateway locally; Django and Vite must already be running."""

import argparse
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from testing.gateway import nginx_gateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, help="Private JSON environment shared with Django"
    )
    parser.add_argument("--backend", default="127.0.0.1:8000")
    parser.add_argument("--frontend", default="127.0.0.1:5173")
    parser.add_argument(
        "--integration",
        help="Explicit Integration upstream; default is the existing backend",
    )
    parser.add_argument("--iam", help="Explicit IAM upstream; default is the existing backend")
    parser.add_argument("--port", type=int, default=8080)
    options = parser.parse_args()
    env = {**os.environ}
    if options.env_file:
        env.update(json.loads(options.env_file.read_text()))
    key = env.get("AICED_GATEWAY_KEY", "")
    with nginx_gateway(
        ROOT / ".local/gateway",
        options.backend,
        options.frontend,
        key,
        options.port,
        integration=options.integration,
        iam=options.iam,
    ) as url:
        print(f"AICED Gateway: {url} (Ctrl+C to stop)", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
