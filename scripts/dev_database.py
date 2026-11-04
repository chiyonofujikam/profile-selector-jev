"""Prepare the local Compose database without discarding its persistent volume.

Used by the development launcher. Credentials come from the root .env and are
never included in subprocess arguments or error messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from dotenv import dotenv_values, set_key
import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url


@dataclass(frozen=True)
class DatabaseConfig:
    database: str
    user: str
    port: int
    password: str = field(repr=False)
    database_url: str = field(repr=False)

    @property
    def environment(self) -> dict[str, str]:
        """Private environment overrides; callers must not log this mapping."""
        return {
            "POSTGRES_DB": self.database,
            "POSTGRES_USER": self.user,
            "POSTGRES_PASSWORD": self.password,
            "POSTGRES_PORT": str(self.port),
            "DATABASE_URL": self.database_url,
        }


def load_database_config(root: Path) -> DatabaseConfig:
    env_file = root / ".env"
    if not env_file.is_file():
        raise RuntimeError("Create the project-root .env and set POSTGRES_PASSWORD before starting.")
    values = dotenv_values(env_file)
    password = values.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError("Set a nonempty POSTGRES_PASSWORD in the project-root .env.")
    database = values.get("POSTGRES_DB") or "jev"
    user = values.get("POSTGRES_USER") or "jev"
    if any(not value.strip() or "\x00" in value or len(value.encode("utf-8")) > 63 for value in (database, user)):
        raise RuntimeError("POSTGRES_DB and POSTGRES_USER must be nonempty PostgreSQL names of at most 63 UTF-8 bytes.")
    try:
        port = int(values.get("POSTGRES_PORT") or "5432")
    except (ValueError, TypeError):
        raise RuntimeError("POSTGRES_PORT must be a number between 1 and 65535.") from None
    if not 1 <= port <= 65535:
        raise RuntimeError("POSTGRES_PORT must be a number between 1 and 65535.")
    url = URL.create(
        "postgresql+psycopg", username=user, password=password,
        host="127.0.0.1", port=port, database=database,
    ).render_as_string(hide_password=False)
    return DatabaseConfig(database=database, user=user, port=port, password=password, database_url=url)


def _run(
    args: list[str], *, root: Path, environment: dict[str, str],
    failure: str, stdin: str | None = None, timeout: float = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args, cwd=root, env=environment, input=stdin, text=True,
            encoding="utf-8", capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError(failure) from None
    if check and result.returncode:
        # psql stderr may contain the submitted password statement. Do not echo it.
        raise RuntimeError(failure)
    return result


def _compose(root: Path, docker: str) -> list[str]:
    return [docker, "compose", "--project-directory", str(root),
            "--env-file", str(root / ".env"), "-f", str(root / "compose.yaml")]


def _previous_bootstrap(
    root: Path, docker: str, compose: list[str], environment: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Remember known bootstrap roles before Compose updates container env values."""
    users: list[str] = []
    databases: list[str] = []
    previous = _run(
        [*compose, "ps", "--all", "--quiet", "postgres"], root=root,
        environment=environment, failure="Could not inspect the PostgreSQL service.", check=False,
    )
    container_id = previous.stdout.strip().splitlines()
    if container_id:
        inspection = _run(
            [docker, "inspect", container_id[0]], root=root, environment=environment,
            failure="Could not inspect the PostgreSQL service.", check=False,
        )
        try:
            metadata = json.loads(inspection.stdout)[0]
            configured = dict(value.split("=", 1) for value in metadata["Config"]["Env"] if "=" in value)
            if configured.get("POSTGRES_USER"):
                users.append(configured["POSTGRES_USER"])
            if configured.get("POSTGRES_DB"):
                databases.append(configured["POSTGRES_DB"])
        except (ValueError, KeyError, TypeError, IndexError):
            pass
    try:
        old_url = make_url(dotenv_values(root / ".env").get("DATABASE_URL") or "")
        if old_url.username:
            users.append(old_url.username)
        if old_url.database:
            databases.append(old_url.database)
    except Exception:
        # A stale URL is replaced after successful provisioning; never echo it.
        pass
    return users, databases


def _psql(
    root: Path, docker: str, container_id: str, environment: dict[str, str],
    user: str, database: str, statement: str, *, check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [docker, "exec", "-i", container_id, "psql", "-X", "-U", user,
         "-d", database, "-Atq", "-v", "ON_ERROR_STOP=1"],
        root=root, environment=environment, stdin=statement, timeout=15, check=check,
        failure="Could not prepare the existing PostgreSQL role/database. The data volume was preserved.",
    )


def _verify_connection(config: DatabaseConfig) -> None:
    for attempt in range(3):
        try:
            # Local sockets and container loopback can use trust authentication.
            # Test the exact authenticated host connection the backend will use.
            with psycopg.connect(
                host="127.0.0.1", port=config.port, dbname=config.database,
                user=config.user, password=config.password, connect_timeout=3,
            ) as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.Error:
            if attempt < 2:
                time.sleep(0.5)
    raise RuntimeError(
        f"PostgreSQL did not accept the backend connection at 127.0.0.1:{config.port}. "
        "Check POSTGRES_PORT and Docker Desktop; existing data was preserved."
    ) from None


def provision_database(root: Path) -> DatabaseConfig:
    """Create/synchronize the configured local role/database, preserving all data."""
    root = root.resolve()
    config = load_database_config(root)
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required. Install/start Docker Desktop, then run the launcher again.")
    environment = {**os.environ, **config.environment}
    compose = _compose(root, docker)
    _run(
        [docker, "info", "--format", "{{.ServerVersion}}"], root=root, environment=environment,
        failure="Docker Desktop is unavailable. Start Docker Desktop and wait for its engine, then retry.",
        timeout=20,
    )
    old_users, old_databases = _previous_bootstrap(root, docker, compose, environment)
    print("Starting PostgreSQL (existing data is retained)...", flush=True)
    _run(
        [*compose, "up", "-d", "--wait", "--wait-timeout", "90", "postgres"],
        root=root, environment=environment, timeout=180,
        failure="PostgreSQL could not start. Check that Docker Desktop is running and POSTGRES_PORT is free.",
    )
    result = _run(
        [*compose, "ps", "--quiet", "postgres"], root=root, environment=environment,
        failure="The PostgreSQL container was not found after startup.",
    )
    container_id = result.stdout.strip()
    if not container_id or "\n" in container_id:
        raise RuntimeError("Expected one local PostgreSQL container; no database changes were attempted.")
    users = list(dict.fromkeys([*old_users, config.user, "postgres"]))
    databases = list(dict.fromkeys(["postgres", *old_databases, config.database, "template1"]))
    administrator: tuple[str, str] | None = None
    for user in users:
        for database in databases:
            probe = _psql(
                root, docker, container_id, environment, user, database,
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user;", check=False,
            )
            if probe.returncode == 0 and probe.stdout.strip() == "t":
                administrator = (user, database)
                break
        if administrator:
            break
    if administrator is None:
        raise RuntimeError(
            "Could not access the existing PostgreSQL administrator. Restore the original POSTGRES_USER "
            "or DATABASE_URL username for this volume, then retry. Existing data was preserved."
        )
    admin_user, admin_database = administrator

    def execute(statement: sql.Composable) -> str:
        return _psql(
            root, docker, container_id, environment, admin_user, admin_database,
            statement.as_string(),
        ).stdout.strip()

    exists = execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = {};").format(sql.Literal(config.user)))
    if not exists:
        execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {};").format(
            sql.Identifier(config.user), sql.Literal(config.password),
        ))
    else:
        execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {};").format(
            sql.Identifier(config.user), sql.Literal(config.password),
        ))
    exists = execute(sql.SQL("SELECT 1 FROM pg_database WHERE datname = {};").format(sql.Literal(config.database)))
    if not exists:
        execute(sql.SQL("CREATE DATABASE {} OWNER {};").format(
            sql.Identifier(config.database), sql.Identifier(config.user),
        ))
    _verify_connection(config)
    if dotenv_values(root / ".env").get("DATABASE_URL") != config.database_url:
        set_key(root / ".env", "DATABASE_URL", config.database_url)
    print(f"PostgreSQL ready at 127.0.0.1:{config.port}; configured password applied.", flush=True)
    return config
