"""Regression guard: the stack-test env gate must not skip pure tests.

tests/stack/conftest.py gates its smoke tests behind INTERPLANT_STACK_TESTS=1.
Its pytest_collection_modifyitems hook receives the WHOLE session item list, so
it must scope skipping to tests/stack/ only. This test fails if the gate ever
again blanket-skips pure tests collected alongside the stack tests.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_stack_gate_does_not_skip_pure_tests():
    env = {k: v for k, v in os.environ.items() if k != "INTERPLANT_STACK_TESTS"}
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/oai/test_formats.py", "tests/stack",
            "-q", "-p", "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # The pure tests/oai/test_formats.py tests must run even though tests/stack
    # is collected (its smoke tests are skipped without the gate). Before the
    # fix the stack gate skipped the whole session, so nothing passed.
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout, (
        "pure tests were skipped by the stack gate:\n" + result.stdout
    )
