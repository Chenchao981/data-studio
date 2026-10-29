"""One pinned FT statistics implementation for every Data Studio CP PAT adapter."""
import hashlib
import importlib
import os
from pathlib import Path
import sys
import zipfile

FORMULA = 'FT_MEDIAN_IQR_6SIGMA_V1'


def ft_pat_engine():
    package = Path(os.environ['STUDIO_FT_PAT_PACKAGE']).resolve(strict=True)
    expected = os.environ['STUDIO_FT_PAT_SHA256']
    with package.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != expected:
            raise ValueError('FT PAT计算包校验失败')
    sys.path.insert(0, str(package))
    engine = importlib.import_module('shared.pat_engine')
    if not Path(engine.__file__).resolve().is_relative_to(package):
        raise ValueError('PAT统计模块没有使用指定的FT计算包')
    with zipfile.ZipFile(package) as archive:
        core_hash = hashlib.sha256(archive.read('shared/pat_engine.py')).hexdigest()
    return engine, {'formula': FORMULA, 'ft_package_sha256': expected,
                    'statistics_module': 'shared.pat_engine', 'statistics_sha256': core_hash,
                    'quartiles': 'pandas linear', 'sigma_divisor': 1.35, 'sigma_multiplier': 6}
