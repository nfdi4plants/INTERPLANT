"""Pin the deployment artefacts against silent drift.

These are the files an operator runs on a box no test can reach, so the checks
here are the only automated statement about them.
"""
from __future__ import annotations

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
    text = (DEPLOY / "interplant-oai.service").read_text(encoding="utf-8")
    assert "0.0.0.0" not in text, "bind the internal address, not every interface"
    assert "192.0.2.10:8000" in text


def test_the_refresh_unit_calls_refresh_not_harvest():
    text = (DEPLOY / "interplant-refresh.service").read_text(encoding="utf-8")
    assert "-m harvester refresh" in text
    assert "harvester harvest" not in text, (
        "harvest writes straight to public.records with no gate; the timer must "
        "use refresh"
    )


def test_the_refresh_unit_has_an_outer_timeout():
    text = (DEPLOY / "interplant-refresh.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=6h" in text, (
        "refresh passes no --parse-timeout, so a single ARC parse is unbounded; "
        "without an outer bound a wedged oneshot blocks every subsequent night"
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
