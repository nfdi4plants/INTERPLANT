"""Render ogc/templates without pygeoapi, in an environment that mirrors it.

pygeoapi 0.23.4 builds its Jinja environment in pygeoapi/util.py
render_j2_template: FileSystemLoader([custom, TEMPLATESDIR, '.']),
extensions=['jinja2.ext.i18n'], autoescape=select_autoescape(), and a fixed
set of filters and globals. CI runs no pygeoapi service, so this harness is
the only place template behaviour is tested there.

Filter NAMES match pygeoapi exactly, so a template that reaches for a filter
pygeoapi does not register fails here the same way it would in production.
Only to_json is implemented, because it is the only one our templates call;
it is copied from pygeoapi, including the < and > rewrite that stops
harvested text from closing a <script> block. The rest raise if called.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = REPO_ROOT / "ogc" / "templates"
CONFIG_PATH = REPO_ROOT / "pygeoapi-config.yml"

_PLACEHOLDER = re.compile(r"\$\{(\w+):-([^}]*)\}")


def _to_json(dict_, pretty=False):
    """Copy of pygeoapi.util.to_json (0.23.4)."""
    dump = json.dumps(
        dict_, default=str, indent=4 if pretty else None, separators=(",", ":")
    )
    return dump.replace("<", "&lt").replace(">", "&gt")


def _not_implemented(*args, **kwargs):
    raise AssertionError(
        "a template called a pygeoapi filter this harness does not implement; "
        "implement it here, copied from pygeoapi/util.py"
    )


_FILTERS = {
    "to_json": _to_json,
    "format_datetime": _not_implemented,
    "format_duration": _not_implemented,
    "human_size": _not_implemented,
    "get_path_basename": _not_implemented,
    "get_breadcrumbs": _not_implemented,
    "filter_dict_by_key_value": _not_implemented,
}
_GLOBALS = ("to_json", "get_path_basename", "get_breadcrumbs", "filter_dict_by_key_value")


def load_config() -> dict:
    """The committed config with ${VAR:-default} expanded, as pygeoapi does."""
    text = _PLACEHOLDER.sub(
        lambda m: os.environ.get(m.group(1), m.group(2)), CONFIG_PATH.read_text()
    )
    return yaml.safe_load(text)


@pytest.fixture(scope="session")
def config() -> dict:
    return load_config()


@pytest.fixture(scope="session")
def env() -> Environment:
    environment = Environment(
        loader=FileSystemLoader([str(TEMPLATE_DIR)]),
        extensions=["jinja2.ext.i18n"],
        autoescape=select_autoescape(),
    )
    environment.filters.update(_FILTERS)
    environment.globals.update({name: _FILTERS[name] for name in _GLOBALS})
    environment.install_null_translations()
    return environment


@pytest.fixture
def render(env: Environment, config: dict):
    def _render(template: str, data: dict) -> str:
        return env.get_template(template).render(
            config=config, data=data, locale="en-US", version="0.23.4"
        )

    return _render
