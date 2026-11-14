"""Local development supervisor for the existing app plus Integration.

Private JSON configuration, no command-line secrets. A routing-file change
gracefully replaces only Nginx, preserving backend/Integration processes.
"""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".tools/python"), str(ROOT / "backend")]
from testing.gateway import nginx_gateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--stop", action="store_true")
    options = parser.parse_args()
    directory = options.directory.resolve()
    if options.stop:
        (directory / "stop").write_text("stop")
        return
    (directory / "stop").unlink(missing_ok=True)
    config = json.loads((directory / "deployment.json").read_text())
    (directory / "supervisor.json").write_text(json.dumps({"pid": os.getpid()}))
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def environment(name):
        return {
            **os.environ,
            **json.loads((directory / name).read_text()),
            "PYTHONPATH": str(ROOT / ".tools/python"),
        }

    backend_env = environment("backend-env.json")
    integration_env = environment("integration-env.json")
    processes = []
    launches = []
    restarted = {}

    def process_status():
        target = directory / "process-status.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    label: {"pid": p.pid, "running": p.poll() is None}
                    for (label, _), p in zip(launches, processes)
                }
            )
        )
        temporary.replace(target)

    with ExitStack() as stack:
        try:
            for label, args, env, cwd in [
                (
                    "backend",
                    [
                        sys.executable,
                        str(ROOT / "backend/manage.py"),
                        "runserver",
                        f"127.0.0.1:{config['backend_port']}",
                        "--noreload",
                    ],
                    backend_env,
                    ROOT,
                ),
                (
                    "iam",
                    [
                        sys.executable,
                        str(ROOT / "backend/manage.py"),
                        "runserver",
                        f"127.0.0.1:{config['iam_port']}",
                        "--noreload",
                        "--settings",
                        "internal_api.settings",
                    ],
                    backend_env,
                    ROOT,
                ),
                (
                    "integration",
                    [
                        sys.executable,
                        str(ROOT / "backend/integration_service/manage.py"),
                        "runserver",
                        f"127.0.0.1:{config['integration_port']}",
                        "--noreload",
                    ],
                    integration_env,
                    ROOT,
                ),
                (
                    "frontend",
                    [
                        str(ROOT / ".tools/node.exe"),
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(config["frontend_port"]),
                        "--strictPort",
                    ],
                    {
                        **backend_env,
                        "API_PROXY_TARGET": f"http://127.0.0.1:{config['backend_port']}",
                    },
                    ROOT / "frontend",
                ),
            ]:
                log = stack.enter_context((directory / (label + ".log")).open("ab"))
                processes.append(
                    subprocess.Popen(
                        args,
                        cwd=cwd,
                        env=env,
                        stdout=log,
                        stderr=log,
                        creationflags=flags,
                    )
                )
                launches.append(
                    (
                        label,
                        dict(
                            args=args,
                            cwd=cwd,
                            env=env,
                            stdout=log,
                            stderr=log,
                            creationflags=flags,
                        ),
                    )
                )
            process_status()
            time.sleep(1)
            while not (directory / "stop").exists():
                mode = json.loads((directory / "deployment.json").read_text())["mode"]
                if mode not in ("service", "legacy"):
                    raise ValueError("Unknown routing mode")
                upstream = (
                    config["integration_port"]
                    if mode == "service"
                    else config["backend_port"]
                )
                with nginx_gateway(
                    directory / "gateway",
                    f"127.0.0.1:{config['backend_port']}",
                    f"127.0.0.1:{config['frontend_port']}",
                    backend_env["AICED_GATEWAY_KEY"],
                    port=config["gateway_port"],
                    integration=f"127.0.0.1:{upstream}",
                ):
                    (directory / "routing-status.json").write_text(
                        json.dumps(
                            {
                                "mode": mode,
                                "gateway_port": config["gateway_port"],
                                "integration_upstream": upstream,
                            }
                        )
                    )
                    while (
                        not (directory / "stop").exists()
                        and json.loads((directory / "deployment.json").read_text())[
                            "mode"
                        ]
                        == mode
                    ):
                        for index, p in enumerate(processes):
                            label, launch = launches[index]
                            if (
                                p.poll() is not None
                                and time.monotonic() - restarted.get(label, 0) > 1
                            ):
                                # A failed Integration process must not take
                                # IAM, Client/CRM or the frontend down with it.
                                processes[index] = subprocess.Popen(**launch)
                                restarted[label] = time.monotonic()
                                process_status()
                        time.sleep(0.25)
        finally:
            for p in processes:
                if p.poll() is None:
                    p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()


if __name__ == "__main__":
    main()
