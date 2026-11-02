"""The manual round-trip script, promoted to a test.

It launches real Chrome with the unpacked extension, so it is skipped when no
Chromium-family browser exists; when one does, this is the only test that proves
export -> import -> re-export through the extension's own code.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from launcher.launch import chrome_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(chrome_path() is None, reason="no Chromium-family browser installed")
def test_live_export_import_roundtrip_and_refusals():
    result = subprocess.run(
        [sys.executable, "tools/live_roundtrip.py"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout
    assert "field differences (excluding derived): []" in result.stdout
    assert "storage unchanged after refusals: True" in result.stdout
