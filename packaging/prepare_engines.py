"""Build an offline, relocatable engine kit from explicitly pinned inputs."""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path

STUDIO=Path(__file__).resolve().parents[1]
REPO=STUDIO/'engine_support'

def copy_sources(root):
    """Refresh only the offline sources owned by this repository."""
    code=root/'code'
    for src in REPO.rglob('*.py'):
        if '__pycache__' in src.parts or 'tests' in src.parts:continue
        dest=code/src.relative_to(REPO)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dest)
    for source,target in [('packaging/studio_runner.py','studio_runner.py'),('packaging/studio_service.py','studio_service.py'),('packaging/studio_viewer.py','studio_viewer.py'),('python_core/result_index.py','studio_result_index.py')]:
        shutil.copyfile(STUDIO/source,code/target)

def verify_files(root, files):
    from concurrent.futures import ThreadPoolExecutor
    def check(item):
        name, expected = item
        if digest(root/name) != expected:
            raise ValueError("Pinned engine file changed: "+name)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(check, files.items()))


def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-only','--local-code-only', dest='source_only', action='store_true', help='Refresh this repository offline sources on a verified engine kit')
    for name in ['runtime','cp','native-ft','shared-ft']:p.add_argument('--'+name,type=Path)
    a=p.parse_args();root=STUDIO/'engines'
    if a.source_only:
        manifest=json.loads((root/'manifest.json').read_text(encoding='utf8'))
        verify_files(root, manifest['files'])
        copy_sources(root)
        write_manifest(root)
        return
    if any(value is None for value in [a.runtime,a.cp,a.native_ft,a.shared_ft]):p.error('Full build requires --runtime --cp --native-ft --shared-ft')
    root.mkdir(exist_ok=True)
    pins=json.loads((STUDIO/'engine-pins.json').read_text())
    for label,path in [('runtime',a.runtime),('cp',a.cp),('native',a.native_ft),('shared',a.shared_ft)]:
        if digest(path)!=pins[label]:raise ValueError('Input checksum mismatch: '+label)
    if not (root/'runtime/python.exe').exists():
        with zipfile.ZipFile(a.runtime) as z:
            for n in z.namelist():
                if not (root/'runtime'/n).resolve().is_relative_to((root/'runtime').resolve()):raise ValueError('Runtime archive path escape')
            z.extractall(root/'runtime')
    (root/'packages').mkdir(exist_ok=True)
    for name,path in [('cp',a.cp),('native',a.native_ft),('shared',a.shared_ft)]:shutil.copyfile(path,root/'packages'/f'{name}.pyz')
    copy_sources(root)
    for name in ['7z.exe','7z.dll','License.txt']:
        src=Path('C:/Program Files/7-Zip')/name
        if src.exists():(root/'tools').mkdir(exist_ok=True);shutil.copyfile(src,root/'tools'/name)

    write_manifest(root)


def write_manifest(root):
    # All CP/FT routes must share the very same approved statistics source.
    # Refuse future packages that accidentally ship divergent PAT algorithms.
    pat_sources = []
    for package in ('native', 'shared'):
        with zipfile.ZipFile(root/'packages'/f'{package}.pyz') as archive:
            pat_sources.append(hashlib.sha256(archive.read('shared/pat_engine.py')).hexdigest())
    if len(set(pat_sources)) != 1:
        raise ValueError('CP/FT共用的PAT统计实现不一致，拒绝生成计算组件')
    program='''import sys,json,dataclasses
from pathlib import Path
r=Path(sys.argv[1]);sys.path[:0]=[str(r/'code'),str(r/'code/backend'),str(r/'code/desktop_client')]
from local_agent.config import AgentConfig
from local_agent.personal_tools import list_capabilities
from nce_desktop.local_native import capabilities, visible
from nce_desktop.local_engines import input_help, desktop_capability
import hashlib
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
tools=[]
for profile in ['native','shared']:
 c=AgentConfig(enable_personal_tools=True,python_runtime=Path(sys.executable),cp_package=r/'packages/cp.pyz',cp_package_sha256=sha(r/'packages/cp.pyz'),ft_package=r/('packages/'+profile+'.pyz'),ft_package_sha256=sha(r/('packages/'+profile+'.pyz')))
 for t in capabilities(c) if profile=='native' else list_capabilities(c):
  selected_profile=profile
  if profile=='shared' and t.factory_code=='JIEMIN' and t.analysis_type=='QUICK_CHART':
   # Charts must parse with the same current Jiemin engine as cleaning/PAT.
   native=dataclasses.replace(c,ft_package=r/'packages/native.pyz',ft_package_sha256=sha(r/'packages/native.pyz'))
   t=next(x for x in list_capabilities(native) if x.tool_code==t.tool_code)
   selected_profile='native'
  t=desktop_capability(t)
  d=dataclasses.asdict(t);d.update(profile=selected_profile,hidden=not visible(t),help=input_help(t).replace('多个文件路径以分号分隔。','多个文件可在文件选择框中一并选中。').replace('基于此结果分析','基于结果生成PAT'));tools.append(d)
print(json.dumps(tools,ensure_ascii=True))'''
    tools=json.loads(subprocess.check_output([str(root/'runtime/python.exe'),'-I','-c',program,str(root)],text=True,encoding='utf8'))
    files={f.relative_to(root).as_posix():digest(f) for prefix in ['code','packages','tools'] for f in (root/prefix).rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    runtime=json.loads((root/'runtime/runtime-manifest.json').read_text())
    verify_files(root/'runtime', {name:item['sha256'] for name,item in runtime['files'].items()})
    files.update({'runtime/'+n:v['sha256'] for n,v in runtime['files'].items()})
    (root/'manifest.json').write_text(json.dumps({'version':'studio-engine-20261030.3','python':'3.13.17','patStatistics':{'module':'shared/pat_engine.py','sha256':pat_sources[0]},'packages':runtime['packages'],'files':files,'tools':tools},ensure_ascii=False,indent=2),encoding='utf8')
    print('Pinned engine kit:',len(tools),'operations;',len(files),'verified files')
    if (root/'viewer-packages').is_dir():
        from prepare_viewer import pin_viewer
        pin_viewer(root)

if __name__=='__main__':main()
