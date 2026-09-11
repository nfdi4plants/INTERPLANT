"""The committed pygeoapi config must carry env-var placeholders, not literals.

Uses pygeoapi's own loader rather than a regex, so the test fails if upstream
ever changes its expansion syntax - which is the thing we actually depend on.
The loader is only present inside the pygeoapi container, so these run as stack
tests and shell out to it.
"""
from __future__ import annotations

import subprocess

import pytest

pytestmark = pytest.mark.db

_LOAD = (
    "import os, sys; "
    "from pygeoapi.util import yaml_load; "
    "cfg = yaml_load(open('/pygeoapi/local.config.yml')); "
    "p = cfg['resources']['arc-locations']['providers'][0]['data']; "
    "print(p['host'], p['password'], cfg['server']['url'])"
)


def _run_in_container(env: dict[str, str] | None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec"]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    # pygeoapi's deps live in a virtualenv at /venv inside the container, not
    # on PATH; `python3` fails with ModuleNotFoundError for jsonschema.
    cmd += ["interplant-pygeoapi", "/venv/bin/python3", "-c", _LOAD]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def test_defaults_resolve_to_the_dev_values() -> None:
    # No environment set: the ${VAR:-default} defaults must reproduce exactly
    # what the dev stack ran on before this change, or dev silently breaks.
    proc = _run_in_container(None)
    assert proc.returncode == 0, proc.stderr
    host, password, url = proc.stdout.split()
    assert host == "db"
    assert password == "interplant"
    assert url == "http://localhost:5000"


def test_environment_overrides_the_defaults() -> None:
    proc = _run_in_container({
        "INTERPLANT_PG_HOST": "prod-db.example.org",
        "INTERPLANT_PG_PASSWORD": "s3cret",
        "INTERPLANT_OGC_BASE_URL": "https://www.plabipd.de/ogc",
    })
    assert proc.returncode == 0, proc.stderr
    host, password, url = proc.stdout.split()
    assert host == "prod-db.example.org"
    assert password == "s3cret"
    assert url == "https://www.plabipd.de/ogc"


def test_no_literal_password_remains_in_the_committed_config() -> None:
    # B3: the whole point is that no credential ships in git. A default inside
    # a ${VAR:-default} is fine; a bare literal is not.
    from pathlib import Path

    text = Path(__file__).parent.parent.parent.joinpath("pygeoapi-config.yml").read_text()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("password:"):
            assert "${" in stripped, f"literal password in committed config: {stripped}"