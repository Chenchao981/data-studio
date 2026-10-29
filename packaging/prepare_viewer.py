"""Validate and pin the separate chart additions without changing core runtime."""
import hashlib,json,subprocess
from pathlib import Path

STUDIO=Path(__file__).resolve().parents[1]


def pin_viewer(root):
    root=Path(root).resolve()
    lock=STUDIO/'environments/cp-viewer.lock'
    packages=dict(line.strip().split('==',1) for line in lock.read_text().splitlines() if line.strip() and not line.startswith('#'))
    program='''import sys,json,importlib.metadata as m
sys.path.insert(0,sys.argv[1])
from packaging.requirements import Requirement
expected=json.loads(sys.argv[2])
for name,version in expected.items():
 assert m.version(name)==version,(name,m.version(name),version)
 for text in m.requires(name) or []:
  req=Requirement(text)
  if req.marker is None or req.marker.evaluate({'extra':''}):
   assert m.version(req.name) in req.specifier,(name,str(req),m.version(req.name))
import streamlit
print('CP viewer dependency graph verified:',streamlit.__version__)
'''
    subprocess.run([str(root/'runtime/python.exe'),'-I','-B','-c',program,str(root/'viewer-packages'),json.dumps(packages)],check=True)
    files={}
    for file in (root/'viewer-packages').rglob('*'):
        if not file.is_file() or '__pycache__' in file.parts or file.suffix=='.pyc':continue
        with file.open('rb') as stream:files[file.relative_to(root).as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()
    if not files:raise ValueError('缺少本地图表依赖')
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf8'))
    manifest['viewer']={'packages':packages,'files':files}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('Pinned viewer files:',len(files))


if __name__=='__main__':pin_viewer(STUDIO/'engines')
