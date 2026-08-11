"""Gating and fixtures for the AWI harvester emulation.

These tests import the portal's own harvester framework from a local read-only
clone of o2a.index.harvester.config, which CI does not have. They are skipped
unless INTERPLANT_PORTAL_TESTS=1 and that clone is present.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_PORTAL_TEST_DIR = Path(__file__).parent
_REPO_ROOT = _PORTAL_TEST_DIR.parent.parent
_GATE = "INTERPLANT_PORTAL_TESTS"
_DEFAULT_O2A = Path.home() / "Mohamed" / "Work" / "INTERPLANT" / "o2a.index.harvester.config"


def o2a_root() -> Path:
    return Path(os.environ.get("INTERPLANT_O2A_PATH", str(_DEFAULT_O2A)))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the emulation tests unless the gate is set and the clone is present.

    pytest passes the whole session's collected items to every conftest hook, so
    this must scope to its own directory. An unscoped loop would skip pure tests
    collected elsewhere - the blanket-skip bug fixed in ea1ccaa.
    """
    if os.environ.get(_GATE) == "1" and (o2a_root() / "harvester" / "helper").is_dir():
        return
    skip_marker = pytest.mark.skip(
        reason=f"set {_GATE}=1 and INTERPLANT_O2A_PATH to a local o2a clone"
    )
    for item in items:
        if item.path.is_relative_to(_PORTAL_TEST_DIR):
            item.add_marker(skip_marker)


@pytest.fixture
def awi_harvester_module():
    """Import portal/harvest-repository-dataplant-arcs.py with their helper package available.

    The clone's `harvester/` directory goes on sys.path first because the script
    does `from helper.OAIHarvester import OAIHarvester`. Bytecode writing is
    disabled so importing cannot create __pycache__ inside the read-only clone.
    """
    sys.dont_write_bytecode = True
    helper_path = str(o2a_root() / "harvester")
    inserted = helper_path not in sys.path
    if inserted:
        sys.path.insert(0, helper_path)

    script = _REPO_ROOT / "portal" / "harvest-repository-dataplant-arcs.py"
    spec = importlib.util.spec_from_file_location("dataplant_arc_harvester", script)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: their Logger.__init__ looks itself up via
    # sys.modules[self.__module__] to find the harvester script's file path.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)
        if inserted and helper_path in sys.path:
            sys.path.remove(helper_path)
