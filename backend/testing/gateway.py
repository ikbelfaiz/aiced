"""Local Nginx harness using exactly the deployment configuration template."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def nginx_gateway(directory, backend, frontend, key, port=None, timeout=120, integration=None, iam=None, commercial=None):
    binary = os.environ.get("NGINX_BINARY") or shutil.which("nginx")
    if not binary:
        candidate = ROOT / ".tools/nginx-1.30.6/nginx.exe"
        if candidate.exists():
            binary = str(candidate)
    if not binary:
        raise RuntimeError(
            "Install Nginx 1.30.6 or set NGINX_BINARY; gateway tests cannot be skipped silently."
        )
    port = port or free_port()
    values = {
        "GATEWAY_PORT": str(port),
        "BACKEND_UPSTREAM": backend,
        "INTEGRATION_UPSTREAM": integration or backend,
        "IAM_UPSTREAM": iam or backend,
        "COMMERCIAL_UPSTREAM": commercial or backend,
        "FRONTEND_UPSTREAM": frontend,
        "AICED_GATEWAY_KEY": key,
        "BACKEND_TIMEOUT": str(timeout),
    }
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", key):
        raise ValueError("Invalid gateway key")
    for value in [backend, frontend, integration or backend, iam or backend, commercial or backend]:
        if not re.fullmatch(r"[A-Za-z0-9.:-]+", value):
            raise ValueError("Invalid upstream")
    if not (0 < port < 65536 and 0 < timeout):
        raise ValueError("Invalid port or timeout")
    directory = Path(directory).resolve()
    for child in ["logs", "temp/client", "temp/proxy"]:
        (directory / child).mkdir(parents=True, exist_ok=True)
    config = (ROOT / "infra/gateway/nginx.conf.template").read_text(encoding="utf-8")
    for name, value in values.items():
        config = config.replace("${" + name + "}", value)
    (directory / "nginx.conf").write_text(config, encoding="utf-8")
    args = [binary, "-p", directory.as_posix() + "/", "-c", "nginx.conf"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (directory / "process.log").open("wb") as log:
        subprocess.run(
            [*args, "-t"], check=True, stdout=log, stderr=log, creationflags=flags
        )
        process = subprocess.Popen(
            [*args, "-g", "daemon off;"], stdout=log, stderr=log, creationflags=flags
        )
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Nginx exited; inspect private process.log")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Nginx did not start")
                    time.sleep(0.05)
            yield f"http://127.0.0.1:{port}"
        finally:
            subprocess.run(
                [*args, "-s", "quit"],
                stdout=log,
                stderr=log,
                creationflags=flags,
                timeout=5,
            )
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Kill the entire Windows Nginx process tree, never unrelated instances.
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=log,
                        stderr=log,
                    )
                else:
                    process.kill()
                process.wait(timeout=5)
