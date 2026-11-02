"""Profile import: what the editor accepts, and what it refuses."""

import json
import subprocess
from pathlib import Path

EXTENSION = Path(__file__).resolve().parent.parent / "extension" / "src"

HARNESS = r"""
import { parseImport } from '%s';
const check = (ok, message) => { if (!ok) { console.error(message); process.exit(1); } };

const raw = parseImport(JSON.stringify({ platform: 'windows', screenX: 1920, screenY: 1080, pixelRatio: 1 }));
check(!raw.error && raw.personas.imported.screenX === 1920, 'a single persona object must import');

const bundle = parseImport(JSON.stringify({ personas: { a: { screenX: 1920 }, b: { screenX: 2560 } } }));
check(Object.keys(bundle.personas).length === 2, 'a bundle must keep both personas');

const wrapped = parseImport(JSON.stringify({ persona: { platform: 'linux' } }));
check(wrapped.personas.imported.platform === 'linux', 'a {persona} wrapper must unwrap');

check(parseImport('{nope').error === 'not valid JSON', 'broken JSON must be refused');
check(parseImport('42').error !== null, 'a scalar must be refused');
check(parseImport(JSON.stringify({ personas: {} })).error !== null, 'an empty bundle must be refused');
console.log('import parser ok');
""" % (EXTENSION / "schema.js").as_uri()


def test_import_parser_accepts_and_refuses_the_right_shapes():
    result = subprocess.run(
        ["node", "--input-type=module", "-e", HARNESS],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "import parser ok" in result.stdout


def test_capability_audit_reports_no_open_items():
    result = subprocess.run(
        ["python3", "tools/capability_audit.py"],
        capture_output=True, text=True, timeout=60,
        cwd=str(EXTENSION.parent.parent),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "missing control ids: 0" in result.stdout
