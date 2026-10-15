"""Pin the deployment artefacts against silent drift.

These are the files an operator runs on a box no test can reach, so the checks
here are the only automated statement about them.
"""
from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def test_requirements_are_hash_pinned():
    text = (DEPLOY / "requirements.txt").read_text(encoding="utf-8")
    assert "--hash=sha256:" in text, "export with `uv export` so installs are verifiable"
    assert "arctrl==3.0.5" in text, "the locked arctrl version must be pinned"


def test_units_run_unprivileged():
    for name in ("interplant-oai.service", "interplant-refresh.service"):
        text = (DEPLOY / name).read_text(encoding="utf-8")
        assert "User=interplant" in text, f"{name} must not run as root"
        assert "EnvironmentFile=/etc/interplant/env" in text


def test_the_endpoint_does_not_bind_all_interfaces():
    unit = (DEPLOY / "interplant-oai.service").read_text(encoding="utf-8")
    assert "--bind ${INTERPLANT_OAI_BIND}" in unit, (
        "the bind address comes from the env file, not from the unit"
    )
    assert "0.0.0.0" not in unit, "bind the internal address, not every interface"
    assert not re.search(r"--bind\s+\d+\.\d+\.\d+\.\d+", unit), (
        "no hardcoded IP in the unit; it is site-specific"
    )

    env_example = (DEPLOY / "interplant.env.example").read_text(encoding="utf-8")
    assert re.search(r"^INTERPLANT_OAI_BIND=.", env_example, re.M)
    assert "INTERPLANT_OAI_BIND=0.0.0.0" not in env_example

    install = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    guard = re.search(r"for _key in ([^;]*); do", install)
    assert guard and "INTERPLANT_OAI_BIND" in guard.group(1).split(), (
        "install.sh must require INTERPLANT_OAI_BIND before installing units"
    )
    assert "0.0.0.0*)" in install, "install.sh must refuse an all-interfaces bind"
    assert guard.start() < install.index("== units =="), (
        "the guard must run before any unit file is installed or restarted"
    )


def test_the_refresh_unit_calls_refresh_not_harvest():
    text = (DEPLOY / "interplant-refresh.service").read_text(encoding="utf-8")
    assert "-m harvester refresh" in text
    assert "harvester harvest" not in text, (
        "harvest writes straight to public.records with no gate; the timer must "
        "use refresh"
    )


def test_the_refresh_unit_bounds_both_a_single_parse_and_the_whole_run():
    text = (DEPLOY / "interplant-refresh.service").read_text(encoding="utf-8")
    assert "--parse-timeout 900" in text, (
        "the four known mega-ARCs are excluded by path, but an unknown fifth "
        "would wedge the nightly exactly as they did; 900s is ~56x the ~16s "
        "typical ARC and 3x the 300s that empirically separated the megas "
        "from every other ARC in a 209-ARC run"
    )
    assert "TimeoutStartSec=4h" in text, (
        "the run is ~30-60 minutes once the mega-ARCs are excluded, but that "
        "estimate covers only ARCs 1-87 of one run; 4h is deliberately loose "
        "until a real run is timed. 6h let seven consecutive nights burn 6h "
        "each without ever publishing"
    )
    assert "--clone-timeout 180" in text, (
        "the 60s default lost 4 ARCs in the 2026-07-29 run; a clone failure "
        "does not fail the run, so a lost ARC is a silently missing record"
    )


def test_the_timer_runs_before_awis_pull():
    text = (DEPLOY / "interplant-refresh.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 02:00:00" in text
    assert "RandomizedDelaySec=" in text


def test_install_script_carries_no_embedded_credential():
    text = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "/etc/interplant/deploy-token" in text, "the token must be read from disk"
    # A deploy token pasted into the script would be committed to git forever.
    assert "glpat-" not in text
    assert "gldt-" not in text
    assert "@gitlab.fz-juelich.de" not in text, (
        "no credentials in the clone URL; the checkout would carry them in .git/config"
    )


def test_install_script_records_the_deployed_commit():
    text = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "DEPLOYED_COMMIT" in text, (
        "without this the VM cannot answer which commit is running"
    )


def test_install_script_stops_before_the_schema_step_on_first_install():
    text = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    write_idx = text.index("WROTE $ENVFILE")
    schema_idx = text.index("== schema ==")
    assert write_idx < schema_idx
    between = text[write_idx:schema_idx]
    assert "exit 1" in between, (
        "a freshly-written env file still has the CHANGE-ME placeholder password; "
        "charging into the schema step would fail with a confusing auth error "
        "instead of stopping cleanly"
    )


def test_the_env_example_carries_no_real_secret():
    text = (DEPLOY / "interplant.env.example").read_text(encoding="utf-8")
    assert "INTERPLANT_DSN=" in text
    assert "INTERPLANT_PG_DSN=" in text
    assert "INTERPLANT_OAI_BASE_URL=" in text
    assert "CHANGE-ME" in text
    assert "interplant:interplant@" not in text, "do not ship the dev password"


def test_the_env_example_header_names_all_three_variables():
    text = (DEPLOY / "interplant.env.example").read_text(encoding="utf-8")
    header = text.split("\n\n", 1)[0]
    assert "INTERPLANT_DSN" in header, "the header must name the endpoint's DSN var"
    assert "INTERPLANT_PG_DSN" in header, "the header must name the harvester's DSN var"
    assert "INTERPLANT_OAI_BASE_URL" in header, (
        "the header must name the third variable too, not just the two DSNs"
    )
    assert "both variables" not in text.lower(), (
        "the file sets three variables, not two; the header must not undercount them"
    )
    # The old header claimed a missing INTERPLANT_PG_DSN "silently falls back
    # to a hardcoded local dev DSN" and "points the writer at the wrong
    # database without saying so" - wrong, and now moot: refresh has no
    # fallback at all, so the header must not resurrect that claim.
    assert "silently falls back" not in text.lower()
    assert "wrong database" not in text.lower()
    assert "refuses" in text.lower(), (
        "the header must say refresh fails closed without INTERPLANT_PG_DSN, "
        "same as the endpoint does without INTERPLANT_DSN"
    )


def test_install_script_restarts_the_endpoint():
    text = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "systemctl restart interplant-oai" in text, (
        "enable --now does not restart an already-running unit, so an upgrade "
        "would leave the old code serving"
    )


def test_install_script_does_not_apply_the_firewall_rules_it_prints():
    lines = (DEPLOY / "install.sh").read_text(encoding="utf-8").splitlines()
    ufw_lines = [line for line in lines if "ufw" in line]
    assert ufw_lines, "install.sh should still tell the operator how to close port 8000"
    # Every ufw mention must be inside an echo string (printed, not executed):
    # install.sh has no proxy address to allow yet, so it cannot safely run
    # these itself, and must not look like it did.
    assert all(line.strip().startswith("echo ") for line in ufw_lines)


def _directive_lines(text: str) -> list[str]:
    """Non-comment, non-blank lines: the unit's actual directives."""
    return [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_refresh_service_has_no_install_section():
    lines = _directive_lines((DEPLOY / "interplant-refresh.service").read_text(encoding="utf-8"))
    assert "[Install]" not in lines, (
        "a oneshot activated only by the timer must not be enable-able "
        "directly; enable on this unit would run a full harvest at every boot"
    )


def test_the_refresh_timer_is_not_persistent():
    lines = _directive_lines((DEPLOY / "interplant-refresh.timer").read_text(encoding="utf-8"))
    assert "Persistent=true" not in lines, (
        "Persistent=true fires a missed 02:00 trigger at boot instead, which "
        "can land a multi-hour harvest's swap inside AWI's 21:03 pull"
    )


def test_readme_does_not_promise_a_third_page():
    text = (DEPLOY / "README.md").read_text(encoding="utf-8")
    assert "three pages" not in text, (
        "PAGE_SIZE=100 over the verified 144-record corpus is two pages; an "
        "operator told to expect a third page that cannot exist will misread a "
        "healthy endpoint as broken"
    )


def test_the_role_password_is_not_interpolated_through_a_c_string():
    text = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for line in text.splitlines():
        if ":'pw'" in line:
            assert " -c " not in line, (
                "psql substitutes :variables only in input it parses itself; a "
                "-c string goes to the server verbatim and the install fails "
                "with `syntax error at or near \":\"`"
            )


def test_script_name_is_scoped_to_the_pygeoapi_unit_only():
    # Both units load /etc/interplant/env and gunicorn reads SCRIPT_NAME from
    # its environment, so a SCRIPT_NAME line in the shared file mounts the OAI
    # endpoint under the OGC prefix too and every /oai request fails with
    # "Configuration problem". This took the public /oai endpoint - the one AWI
    # harvests - down on 2026-09-14.
    env_example = (DEPLOY / "interplant.env.example").read_text(encoding="utf-8")
    for line in env_example.splitlines():
        assert not line.strip().startswith("SCRIPT_NAME="), (
            "SCRIPT_NAME must not live in the shared env file; set it with "
            "Environment= in interplant-pygeoapi.service instead"
        )

    pygeoapi = (DEPLOY / "interplant-pygeoapi.service").read_text(encoding="utf-8")
    assert "Environment=SCRIPT_NAME=/ogc" in pygeoapi, (
        "the OGC API is mounted under a path prefix; without this the proxy's "
        "/ogc requests reach an app serving at /"
    )
    # Order matters: systemd applies Environment= and EnvironmentFile= in the
    # order written, so this must come after the file to override a stray value.
    assert pygeoapi.index("EnvironmentFile=") < pygeoapi.index("Environment=SCRIPT_NAME=")

    oai = (DEPLOY / "interplant-oai.service").read_text(encoding="utf-8")
    assert "SCRIPT_NAME" not in oai, "the OAI endpoint serves at /, with no prefix"
