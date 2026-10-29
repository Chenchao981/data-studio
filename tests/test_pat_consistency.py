"""Future package refreshes must not split the CP/FT statistics implementation."""
from pathlib import Path
import runpy
import zipfile

import pytest


def test_reject_divergent_ft_pat_implementations_before_build(tmp_path):
    package = tmp_path/'packages';package.mkdir()
    for name, code in [('native','six_sigma'),('shared','different_algorithm')]:
        with zipfile.ZipFile(package/f'{name}.pyz','w') as z:
            z.writestr('shared/pat_engine.py',code)
    source = Path(__file__).resolve().parents[1]/'packaging/prepare_engines.py'
    prepare = runpy.run_path(str(source))
    with pytest.raises(ValueError,match='PAT统计实现不一致'):
        prepare['write_manifest'](tmp_path)
    assert not (tmp_path/'manifest.json').exists()
