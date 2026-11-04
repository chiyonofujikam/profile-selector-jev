"""Local stack launcher. On Windows use run.cmd or run.ps1 from any directory."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
from threading import Thread
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from dotenv import dotenv_values, set_key

from scripts.dev_database import provision_database

ROOT = Path(__file__).resolve().parents[1]


def ensure_environment_file(root: Path) -> None:
    path = root / ".env"
    values = dotenv_values(path) if path.exists() else {}
    if values.get("POSTGRES_PASSWORD"):
        return
    if not sys.stdin.isatty():
        raise RuntimeError("Set POSTGRES_PASSWORD in the root .env, then rerun the launcher.")
    password = getpass.getpass("PostgreSQL password (hidden): ")
    if not password:
        raise RuntimeError("The PostgreSQL password cannot be empty.")
    if not path.exists():
        path.write_text(
            "DECISION_PROVIDER=mock\nPOSTGRES_DB=jev\nPOSTGRES_USER=jev\nPOSTGRES_PORT=5432\n",
            encoding="utf-8",
        )
    set_key(path, "POSTGRES_PASSWORD", password)


def run_checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode}). See the output above.")


def ensure_frontend_dependencies(root: Path, npm: str) -> None:
    frontend = root / "frontend"
    signature = hashlib.sha256(
        (frontend / "package.json").read_bytes() + (frontend / "package-lock.json").read_bytes()
    ).hexdigest()
    stamp = frontend / "node_modules" / ".jev-install-signature"
    if stamp.exists() and stamp.read_text(encoding="utf-8").strip() == signature:
        return
    print("Installing/checking frontend dependencies...", flush=True)
    run_checked([npm, "ci", "--no-fund", "--no-audit"], cwd=frontend)
    stamp.write_text(signature, encoding="utf-8")


def http_json(url: str) -> dict | None:
    try:
        with urlopen(url, timeout=2) as response:
            payload = json.load(response)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, HTTPError, URLError):
        return None


def backend_ready(port: int) -> bool:
    health = http_json(f"http://127.0.0.1:{port}/health")
    if not health or not health.get("database", {}).get("ready"):
        return False
    config = http_json(f"http://127.0.0.1:{port}/api/v1/config")
    return bool(config and config.get("provider") in {"mock", "jev"} and "policy_version" in config)


def frontend_ready(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            return "Smart Filter Selector" in response.read(65536).decode("utf-8", errors="replace")
    except (OSError, HTTPError, URLError):
        return False


def port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


@dataclass
class Service:
    name: str
    process: subprocess.Popen


def start_service(name: str, command: list[str], *, cwd: Path, env: dict[str, str]) -> Service:
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(
        command, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", **options,
    )

    def forward_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            print(f"[{name}] {line.rstrip()}", flush=True)

    Thread(target=forward_output, daemon=True).start()
    return Service(name, process)


def stop_owned(services: list[Service]) -> None:
    for service in reversed(services):
        process = service.process
        if process.poll() is not None:
            continue
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_ready(service: Service, check, *, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if service.process.poll() is not None:
            raise RuntimeError(f"{service.name} exited during startup. See its output above.")
        if check():
            return
        time.sleep(0.4)
    raise RuntimeError(f"{service.name} did not become ready within {timeout:g} seconds.")


def run_services(root: Path, npm: str, environment: dict[str, str], backend_port: int, frontend_port: int) -> int:
    owned: list[Service] = []
    try:
        if backend_ready(backend_port):
            print(f"Backend already running on port {backend_port}; reusing it.", flush=True)
        else:
            if not port_available(backend_port):
                raise RuntimeError(f"Port {backend_port} is occupied by a service that is not a ready Jev backend. Stop it, or use -BackendPort with another port.")
            service = start_service("backend", [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--reload", "--host", "127.0.0.1", "--port", str(backend_port)], cwd=root, env=environment)
            owned.append(service)
            wait_ready(service, lambda: backend_ready(backend_port))

        if frontend_ready(frontend_port):
            print(f"Frontend already running on port {frontend_port}; reusing it.", flush=True)
        else:
            if not port_available(frontend_port):
                raise RuntimeError(f"Port {frontend_port} is occupied by another service. Stop it, or use -FrontendPort with another port.")
            service = start_service("frontend", [npm, "run", "dev", "--", "--port", str(frontend_port), "--strictPort"], cwd=root / "frontend", env=environment)
            owned.append(service)
            wait_ready(service, lambda: frontend_ready(frontend_port))

        print(f"\nFrontend: http://127.0.0.1:{frontend_port}\nAPI docs: http://127.0.0.1:{backend_port}/docs", flush=True)
        if not owned:
            print("Both services are already running.", flush=True)
            return 0
        print("Press Ctrl+C to stop services started by this launcher. PostgreSQL data stays in Docker.\n", flush=True)
        while True:
            for service in owned:
                if service.process.poll() is not None:
                    raise RuntimeError(f"{service.name} stopped (exit {service.process.returncode}).")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping application services...", flush=True)
        return 0
    finally:
        stop_owned(owned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args(argv)
    if not all(1 <= port <= 65535 for port in (args.backend_port, args.frontend_port)) or args.backend_port == args.frontend_port:
        parser.error("Use distinct backend/frontend ports between 1 and 65535.")
    try:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm or not shutil.which("node"):
            raise RuntimeError("Node.js and npm are required. Install Node.js, reopen the terminal, and rerun.")
        if not shutil.which("docker"):
            raise RuntimeError("Docker Desktop is required. Install/start it and rerun.")
        ensure_environment_file(ROOT)
        print("Starting PostgreSQL and preparing your configured database...", flush=True)
        database = provision_database(ROOT)
        environment = {**os.environ, **database.environment}
        allowed = (dotenv_values(ROOT / ".env").get("ALLOWED_ORIGINS") or "").split(",")
        environment["ALLOWED_ORIGINS"] = ",".join(dict.fromkeys([value.strip() for value in allowed if value.strip()] + [f"http://127.0.0.1:{args.frontend_port}", f"http://localhost:{args.frontend_port}"]))
        environment["VITE_API_URL"] = f"http://127.0.0.1:{args.backend_port}"
        print("Applying database migrations...", flush=True)
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=environment)
        ensure_frontend_dependencies(ROOT, npm)
        if args.setup_only:
            print("Setup complete. Database and dependencies are ready.", flush=True)
            return 0
        return run_services(ROOT, npm, environment, args.backend_port, args.frontend_port)
    except KeyboardInterrupt:
        print("\nStartup cancelled.", flush=True)
        return 130
    except (RuntimeError, OSError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
