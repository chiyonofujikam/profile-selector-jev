"""Isolated launcher checks; never start servers or insert product data."""

import json
import subprocess
from types import SimpleNamespace

from dotenv import dotenv_values, set_key
import pytest
from sqlalchemy.engine import make_url

from scripts import dev, dev_database


@pytest.fixture
def launch_root(tmp_path):
    path = tmp_path / ".env"
    path.write_text("POSTGRES_DB=fixture_db\nPOSTGRES_USER=fixture_user\nPOSTGRES_PORT=6543\n", encoding="utf-8")
    set_key(path, "POSTGRES_PASSWORD", "Fixture 'quoted' :/@?#% \\ password")
    return tmp_path


def test_password_round_trips_in_url_and_is_absent_from_config_repr(launch_root):
    config = dev_database.load_database_config(launch_root)
    parsed = make_url(config.database_url)
    assert parsed.password == dotenv_values(launch_root / ".env")["POSTGRES_PASSWORD"]
    assert parsed.username == "fixture_user"
    assert parsed.database == "fixture_db"
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 6543
    assert config.password not in repr(config)
    assert config.database_url not in repr(config)


@pytest.mark.parametrize("key,value", [
    ("POSTGRES_PASSWORD", ""),
    ("POSTGRES_PORT", "not-a-port"),
    ("POSTGRES_PORT", "65536"),
    ("POSTGRES_USER", "x" * 64),
])
def test_invalid_database_configuration_fails_before_running_commands(launch_root, key, value, monkeypatch):
    set_key(launch_root / ".env", key, value)
    monkeypatch.setattr(dev_database.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("No command should run"))
    with pytest.raises(RuntimeError):
        dev_database.load_database_config(launch_root)


def test_failed_database_command_suppresses_secret_sql_and_errors(launch_root, monkeypatch):
    private = "Fixture password must not be echoed"
    monkeypatch.setattr(dev_database.subprocess, "run", lambda args, **_kwargs: subprocess.CompletedProcess(args, 1, private, private))
    with pytest.raises(RuntimeError) as captured:
        dev_database._run(["docker", "exec", "fixture"], root=launch_root, environment={},
                          stdin="ALTER ROLE fixture PASSWORD '" + private + "';", failure="Database setup failed")
    assert str(captured.value) == "Database setup failed"
    assert private not in str(captured.value)


@pytest.mark.parametrize("already_exists", [False, True])
def test_database_provisioning_creates_or_updates_without_dropping_data(launch_root, monkeypatch, already_exists):
    config = dev_database.load_database_config(launch_root)
    calls = []
    verified = []
    monkeypatch.setattr(dev_database.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(dev_database, "_verify_connection", lambda value: verified.append(value))

    def command(args, *, stdin=None, **_kwargs):
        calls.append((args, stdin))
        if "inspect" in args:
            output = json.dumps([{"Config": {"Env": ["POSTGRES_USER=fixture_admin", "POSTGRES_DB=fixture_old"]}}])
        elif "ps" in args:
            output = "fixture-container\n"
        elif stdin and "SELECT rolsuper" in stdin:
            output = "t\n"
        elif stdin and ("FROM pg_roles WHERE rolname =" in stdin or "FROM pg_database WHERE datname =" in stdin):
            output = "1\n" if already_exists else ""
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(dev_database, "_run", command)
    result = dev_database.provision_database(launch_root)
    statements = [statement for _, statement in calls if statement]
    assert result == config
    assert verified == [config]
    assert make_url(dotenv_values(launch_root / ".env")["DATABASE_URL"]).password == config.password
    assert all(config.password not in " ".join(arguments) for arguments, _ in calls)
    assert not any("DROP " in statement.upper() for statement in statements)
    assert any("ALTER ROLE" in statement for statement in statements) is already_exists
    assert any("CREATE ROLE" in statement for statement in statements) is not already_exists
    assert any("CREATE DATABASE" in statement for statement in statements) is not already_exists


def test_setup_only_provisions_and_migrates_without_starting_servers(launch_root, monkeypatch):
    config = dev_database.load_database_config(launch_root)
    commands = []
    monkeypatch.setattr(dev, "ROOT", launch_root)
    monkeypatch.setattr(dev.shutil, "which", lambda name: name)
    monkeypatch.setattr(dev, "ensure_environment_file", lambda _root: None)
    monkeypatch.setattr(dev, "provision_database", lambda _root: config)
    monkeypatch.setattr(dev, "ensure_frontend_dependencies", lambda *_args: None)
    monkeypatch.setattr(dev, "run_checked", lambda command, **kwargs: commands.append((command, kwargs)))
    monkeypatch.setattr(dev, "run_services", lambda *_args: pytest.fail("Setup-only must not launch application servers"))
    assert dev.main(["--setup-only", "--backend-port", "8002", "--frontend-port", "5175"]) == 0
    assert commands[0][0][-4:] == ["-m", "alembic", "upgrade", "head"]
    assert commands[0][1]["env"]["DATABASE_URL"] == config.database_url
    assert commands[0][1]["env"]["VITE_API_URL"] == "http://127.0.0.1:8002"


def test_launcher_applies_env_file_over_old_terminal_provider(launch_root, monkeypatch):
    set_key(launch_root / ".env", "DECISION_PROVIDER", "jev")
    monkeypatch.setenv("DECISION_PROVIDER", "mock")
    config = dev_database.load_database_config(launch_root)
    commands = []
    monkeypatch.setattr(dev, "ROOT", launch_root)
    monkeypatch.setattr(dev.shutil, "which", lambda name: name)
    monkeypatch.setattr(dev, "ensure_environment_file", lambda _root: None)
    monkeypatch.setattr(dev, "provision_database", lambda _root: config)
    monkeypatch.setattr(dev, "ensure_frontend_dependencies", lambda *_args: None)
    monkeypatch.setattr(dev, "run_checked", lambda command, **kwargs: commands.append(kwargs))
    assert dev.main(["--setup-only"]) == 0
    assert commands[0]["env"]["DECISION_PROVIDER"] == "jev"


def test_demo_mode_seeds_after_migrations_without_starting_servers(launch_root, monkeypatch):
    config = dev_database.load_database_config(launch_root)
    commands = []
    monkeypatch.setattr(dev, "ROOT", launch_root)
    monkeypatch.setattr(dev.shutil, "which", lambda name: name)
    monkeypatch.setattr(dev, "ensure_environment_file", lambda _root: None)
    monkeypatch.setattr(dev, "provision_database", lambda _root: config)
    monkeypatch.setattr(dev, "ensure_frontend_dependencies", lambda *_args: None)
    monkeypatch.setattr(dev, "run_checked", lambda command, **kwargs: commands.append((command, kwargs)))
    monkeypatch.setattr(dev, "run_services", lambda *_args: pytest.fail("Setup-only must not start servers"))
    assert dev.main(["--setup-only", "--demo"]) == 0
    assert commands[0][0][-4:] == ["-m", "alembic", "upgrade", "head"]
    assert commands[1][0][-2:] == ["-m", "scripts.seed_demo"]
    assert commands[1][1]["env"]["DATABASE_URL"] == config.database_url


def test_healthy_existing_services_are_reused_and_never_owned(launch_root, monkeypatch):
    cleanup = []
    monkeypatch.setattr(dev, "backend_ready", lambda _port, **_kwargs: True)
    monkeypatch.setattr(dev, "frontend_ready", lambda _port: True)
    monkeypatch.setattr(dev, "start_service", lambda *_args, **_kwargs: pytest.fail("Do not duplicate existing services"))
    monkeypatch.setattr(dev, "stop_owned", lambda services: cleanup.append(list(services)))
    assert dev.run_services(launch_root, "npm", {}, 8000, 5173) == 0
    assert cleanup == [[]]


def test_startup_failure_cleans_up_only_the_started_backend(launch_root, monkeypatch):
    backend = dev.Service("backend", SimpleNamespace())
    cleanup = []
    monkeypatch.setattr(dev, "backend_ready", lambda _port, **_kwargs: False)
    monkeypatch.setattr(dev, "frontend_ready", lambda _port: False)
    monkeypatch.setattr(dev, "port_available", lambda _port: True)
    monkeypatch.setattr(dev, "wait_ready", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dev, "stop_owned", lambda services: cleanup.append(list(services)))

    def start(name, *_args, **_kwargs):
        if name == "backend":
            return backend
        raise RuntimeError("Frontend startup fixture failure")

    monkeypatch.setattr(dev, "start_service", start)
    with pytest.raises(RuntimeError, match="Frontend startup fixture failure"):
        dev.run_services(launch_root, "npm", {}, 8000, 5173)
    assert cleanup == [[backend]]


def test_ctrl_c_stops_owned_frontend_but_leaves_reused_backend(launch_root, monkeypatch):
    frontend = dev.Service("frontend", SimpleNamespace(poll=lambda: None))
    cleanup = []
    monkeypatch.setattr(dev, "backend_ready", lambda _port, **_kwargs: True)
    monkeypatch.setattr(dev, "frontend_ready", lambda _port: False)
    monkeypatch.setattr(dev, "port_available", lambda _port: True)
    monkeypatch.setattr(dev, "start_service", lambda *_args, **_kwargs: frontend)
    monkeypatch.setattr(dev, "wait_ready", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dev, "stop_owned", lambda services: cleanup.append(list(services)))
    monkeypatch.setattr(dev.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert dev.run_services(launch_root, "npm", {}, 8000, 5173) == 0
    assert cleanup == [[frontend]]


def test_unrelated_occupied_backend_port_is_not_taken_over(launch_root, monkeypatch):
    cleanup = []
    monkeypatch.setattr(dev, "backend_ready", lambda _port, **_kwargs: False)
    monkeypatch.setattr(dev, "port_available", lambda _port: False)
    monkeypatch.setattr(dev, "start_service", lambda *_args, **_kwargs: pytest.fail("Do not take over another service"))
    monkeypatch.setattr(dev, "stop_owned", lambda services: cleanup.append(list(services)))
    with pytest.raises(RuntimeError, match="occupied"):
        dev.run_services(launch_root, "npm", {}, 8000, 5173)
    assert cleanup == [[]]


@pytest.mark.parametrize("running,provider,model,expected", [
    ({"provider": "mock", "model": "deterministic-demo"}, "jev", "jev-latest", False),
    ({"provider": "jev", "model": "jev-latest"}, "jev", "jev-latest", True),
    ({"provider": "jev", "model": "jev-preview"}, "jev", "jev-latest", False),
    ({"provider": "mock", "model": "deterministic-demo"}, "mock", "jev-latest", True),
])
def test_backend_readiness_checks_the_requested_provider_and_model(monkeypatch, running, provider, model, expected):
    def response(url):
        if url.endswith("/health"):
            return {"database": {"ready": True}}
        return {**running, "policy_version": "fixture"}
    monkeypatch.setattr(dev, "http_json", response)
    assert dev.backend_ready(8000, provider=provider, model=model) is expected


def test_stale_mock_backend_is_not_reused_for_jev(launch_root, monkeypatch):
    set_key(launch_root / ".env", "DECISION_PROVIDER", "jev")
    cleanup = []
    monkeypatch.setattr(dev, "backend_ready", lambda _port, **kwargs: kwargs.get("provider") is None)
    monkeypatch.setattr(dev, "port_available", lambda _port: False)
    monkeypatch.setattr(dev, "start_service", lambda *_args, **_kwargs: pytest.fail("Do not start over an existing backend"))
    monkeypatch.setattr(dev, "stop_owned", lambda services: cleanup.append(list(services)))
    with pytest.raises(RuntimeError, match="different Jev settings"):
        dev.run_services(launch_root, "npm", {}, 8000, 5173)
    assert cleanup == [[]]
