"""The validation CLI must bind its kit inside the actual spawn worker."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('missing', [False, True])
def test_spawn_rejects_bad_target_kit_without_falling_back(tmp_path, missing):
    kit = tmp_path / '独立 kit'
    (kit / 'runtime').mkdir(parents=True)
    (kit / 'packages').mkdir()
    (kit / 'runtime/python.exe').write_bytes(b'not executed')
    if not missing:
        (kit / 'packages/cp.pyz').write_bytes(b'tampered')
    manifest = json.loads((ROOT / 'engines/manifest.json').read_text(encoding='utf8'))
    manifest['files'] = {
        'runtime/python.exe': hashlib.sha256(b'not executed').hexdigest(),
        'packages/cp.pyz': hashlib.sha256(b'original').hexdigest(),
    }
    (kit / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    source = tmp_path / 'sample.zip'
    source.write_bytes(b'not parsed because target integrity must fail first')
    result = subprocess.run([
        sys.executable, str(ROOT / 'tests/run_standalone_smoke.py'),
        '--kit', str(kit), '--source', str(source),
        '--tool', 'LOCAL_CP_HUAHONG_RAW_PAT_V1', '--home', str(tmp_path / 'home'),
    ], capture_output=True, encoding='utf8', env={**os.environ, 'PYTHONUTF8': '1'}, timeout=40)
    assert result.returncode != 0
    task = json.loads(result.stdout)
    assert task['status'] == 'FAILED'
    assert 'cp.pyz' in task['error']
    assert not list((tmp_path / 'home-exports').iterdir())


def test_product_engine_ignores_validation_environment(tmp_path):
    result = subprocess.run([
        sys.executable, '-c', 'from python_core.engine import engine_root; print(engine_root())',
    ], cwd=ROOT, capture_output=True, encoding='utf8', check=True,
        env={**os.environ, 'STUDIO_VALIDATION_ENGINE_KIT': str(tmp_path)})
    assert Path(result.stdout.strip()) == ROOT / 'engines'
