"""The committed pygeoapi config must carry env-var placeholders, not literals.

Uses pygeoapi's own loader rather than a regex, so the test fails if upstream
ever changes its expansion syntax - which is the thing we actually depend on.
The loader is only present inside the pygeoapi container, so these run as stack
tests and shell out to it.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        shutil.which("docker") is None,
        reason="needs the docker dev stack (docker exec into the pygeoapi container)",
    ),
]

_LOAD = (
    "import os, sys; "
    "from pygeoapi.util import yaml_load; "
    "cfg = yaml_load(open('/pygeoapi/local.config.yml')); "
    "p = cfg['resources']['arc-locations']['providers'][0]['data']; "
    "print(p['host'], p['password'], cfg['server']['url'])"
)

_FORCE_ROOT = (
    "import pathlib; "
    "from pygeoapi.util import yaml_load; "
    "pathlib.Path('/tmp/cfg-unset.yml').write_text('a: ${INTERPLANT_NEVER_SET_VAR}\\n'); "
    "yaml_load(open('/tmp/cfg-unset.yml'))"
)


def _run_in_container(env: dict[str, str] | None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec"]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd += ["interplant-pygeoapi"]
    if env is None:
        # compose.yaml sets these in the container and `docker exec` inherits
        # them, so without an explicit unset the None branch reads the override
        # path and never exercises a ${VAR:-default} at all (verified: a bogus
        # default still resolved to the overridden 'db').
        cmd += [
            "env",
            "-u", "INTERPLANT_PG_HOST",
            "-u", "INTERPLANT_PG_PASSWORD",
            "-u", "INTERPLANT_OGC_BASE_URL",
        ]
    # pygeoapi's deps live in a virtualenv at /venv inside the container, not
    # on PATH; `python3` fails with ModuleNotFoundError for jsonschema.
    cmd += ["/venv/bin/python3", "-c", _LOAD]
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


def test_an_unset_variable_with_no_default_fails_loudly() -> None:
    # D2: a misconfigured production box must fail loudly at startup. pygeoapi's
    # env_constructor raises EnvironmentError naming the variable when it is
    # unset and no default is present; the traceback must land on stderr.
    proc = subprocess.run(
        ["docker", "exec", "interplant-pygeoapi", "/venv/bin/python3", "-c", _FORCE_ROOT],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "INTERPLANT_NEVER_SET_VAR" in proc.stderr