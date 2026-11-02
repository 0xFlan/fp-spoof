"""The popup's own controls must survive into a launched Chrome.

The tool drives the real popup page (city select, route select, Save), exports
the resolved persona through the extension's own schema module, launches Chrome
through the launcher, and compares observed values plus the actual proxy/direct
routes. This wrapper keeps that run inside the normal test suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from launcher.launch import chrome_path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "gui_roundtrip.py"

pytestmark = pytest.mark.skipif(
    chrome_path() is None or not (REPO / "extension" / "manifest.json").exists(),
    reason="needs Chrome and the unpacked extension",
)


def test_gui_authoring_survives_into_launched_chrome():
    result = subprocess.run(
        [sys.executable, str(TOOL)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=240,
    )
    output = result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout, output
    assert result.returncode == 0, output
