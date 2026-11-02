"""Store and CLI tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from models import store

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def temp_home(tmp_path, monkeypatch):
    store.close()
    monkeypatch.setenv("FPSPOOF_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FPSPOOF_DB", raising=False)
    yield tmp_path
    store.close()


def test_database_lives_under_fp_spoof_home(temp_home):
    assert str(store.db_path()).startswith(str(temp_home))
    assert "dd2dl" not in str(store.db_path())


def test_schema_is_created_lazily_and_safely(temp_home):
    assert store.list_profiles() == []
    assert store.count() == 0


def test_upsert_is_idempotent(temp_home):
    store.upsert(name="a", browser="chrome", platform="windows", entropy=21.5, fpjs=1.0, persona={"x": 1})
    store.upsert(name="a", browser="chrome", platform="windows", entropy=22.0, fpjs=1.0, persona={"x": 2})
    rows = store.list_profiles()
    assert len(rows) == 1
    assert rows[0]["entropy_bits"] == 22.0
    assert rows[0]["persona"] == {"x": 2}


def test_created_timestamp_is_real(temp_home):
    store.upsert(name="b", browser="chrome", platform="windows", persona={})
    row = store.get("b")
    assert row["created"].startswith("20")
    assert row["created"] != "2026-10-01T00:00:00Z"


def test_persona_payload_roundtrips(temp_home):
    persona = {"screenX": 1920, "plugins": ["PDF Viewer"], "deviceMemory": None}
    store.upsert(name="c", browser="safari", platform="mac", persona=persona)
    assert store.get("c")["persona"] == persona


def test_delete_and_hits(temp_home):
    store.upsert(name="d", browser="chrome", platform="windows", persona={})
    store.bump_hits("d")
    assert store.get("d")["hits"] == 1
    assert store.delete("d") is True
    assert store.get("d") is None
    assert store.delete("d") is False


REPO_MIRROR = REPO / "extension" / "personas.json"
REPO_BOMB = REPO / "extension" / "src" / "persona.js"


@pytest.fixture(autouse=True)
def _never_write_the_working_tree():
    """A test run must not rewrite the extension shipped in the repo."""
    before = (REPO_MIRROR.read_text(), REPO_BOMB.read_text())
    yield
    after = (REPO_MIRROR.read_text(), REPO_BOMB.read_text())
    assert after == before, "a test rewrote extension/personas.json or persona.js"


def _run(args, env):
    env = dict(env)
    # Every CLI subprocess writes a mirror; keep it out of the working tree.
    env.setdefault("FPSPOOF_EXTENSION", str(Path(env["FPSPOOF_HOME"]).parent / "extension"))
    return subprocess.run(
        [sys.executable, "-m", "api.cli"] + args,
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_generates_every_combo(temp_home):
    env = dict(os.environ, FPSPOOF_HOME=str(temp_home / "home"))
    result = _run(["gen", "--all", "--json"], env)
    assert result.returncode == 0, result.stderr
    created = json.loads(result.stdout)
    assert len(created) == 8
    assert all(item["entropy_bits"] > 0 for item in created)
    assert all(item["score"] == 1.0 for item in created)

    listing = _run(["list", "--json"], env)
    assert listing.returncode == 0, listing.stderr
    assert len(json.loads(listing.stdout)) == 8


def test_cli_validate_and_export(temp_home):
    env = dict(os.environ, FPSPOOF_HOME=str(temp_home / "home"))
    assert _run(["gen", "-n", "3"], env).returncode == 0
    validate = _run(["validate", "--json"], env)
    assert validate.returncode == 0, validate.stderr
    report = json.loads(validate.stdout)
    assert all(entry["ok"] for entry in report)

    target = temp_home / "bundle.json"
    export = _run(["export", "--out", str(target)], env)
    assert export.returncode == 0, export.stderr
    bundle = json.loads(target.read_text())
    assert len(bundle["personas"]) == 3


def test_cli_rejects_impossible_combo(temp_home):
    env = dict(os.environ, FPSPOOF_HOME=str(temp_home / "home"))
    result = _run(["gen", "-b", "safari", "-p", "windows"], env)
    assert result.returncode == 2
    assert "not available" in result.stderr


def test_mirror_written_for_extension(temp_home):
    extension = temp_home / "extension"
    extension.mkdir()
    (extension / "src").mkdir()
    env = dict(os.environ,
               FPSPOOF_HOME=str(temp_home / "home"),
               FPSPOOF_EXTENSION=str(extension))
    assert _run(["gen"], env).returncode == 0

    payload = json.loads((extension / "personas.json").read_text())
    assert payload["personas"]
    assert payload["default"] in payload["personas"]
    # the document_start bomb is written alongside the mirror
    assert "__FPS_PERSONA__" in (extension / "src" / "persona.js").read_text()

