"""Compare original and pooled tasks, including shared FT's nested result ZIP."""
import argparse,gzip,json,statistics
from pathlib import Path
from zipfile import ZipFile
from reconcile_cleaning_speed import compare,digest


def business_files(task,temporary):
    direct=[Path(a['path']) for a in task['artifacts'] if Path(a['path']).suffix in {'.csv','.xlsx'}]
    if direct:return direct,[]
    files,metadata=[],[]
    for artifact in task['artifacts']:
        if not artifact['name'].endswith('.zip'):continue
        with ZipFile(artifact['path']) as z:
            for name in z.namelist():
                target=(temporary/name).resolve()
                assert target.is_relative_to(temporary.resolve())
                if name.endswith(('.csv','.xlsx','.csv.gz')):
                    target.parent.mkdir(parents=True,exist_ok=True);data=z.read(name)
                    if name.endswith('.gz'):data=gzip.decompress(data);target=target.with_suffix('')
                    target.write_bytes(data);files.append(target)
                elif name.endswith('ft_scatter_manifest.json'):
                    record=json.loads(z.read(name));record.pop('created_at',None);metadata.append(record)
    assert files,'No business files were compared'
    return files,metadata


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    old=json.loads((a.baseline/'validation.json').read_text(encoding='utf8'));new=json.loads((a.candidate/'validation.json').read_text(encoding='utf8'));assert len(old)==len(new)
    matched=[];scratch=a.output.parent/'reconciled-files'
    for before,after in zip(old,new):
        name=after['validationCase'];assert name==before['validationCase']
        left,lmeta=business_files(before,scratch/name/'old');right,rmeta=business_files(after,scratch/name/'new')
        count=compare(left,right);assert count>0 and lmeta==rmeta
        x=json.loads((Path(before['output']).parent/'receipt.json').read_text(encoding='utf8'));y=json.loads((Path(after['output']).parent/'receipt.json').read_text(encoding='utf8'))
        assert x['result']['business_identity']==y['result']['business_identity']
        # FT single-file selection has a private directory copy per task. Copy
        # timestamps differ by design; source name, size and bytes must match.
        def fingerprint(r):return [{k:v for k,v in f.items() if k!='mtime_ns'} for f in r['inputFingerprint']]
        assert fingerprint(x)==fingerprint(y)
        for source,checksum in y['selectedOriginals'].items():assert digest(Path(source))==checksum
        for artifact in after['artifacts']:assert digest(Path(artifact['path']))==artifact['sha256']
        matched.append({'case':name,'csvCellsOrXlsxParts':count,'businessIdentity':y['result']['business_identity'],'worker':after['computeWorker']})
    summary={}
    workers={}
    for t in new:
        w=t['computeWorker'];workers.setdefault((w['stage'],w['profile']),set()).add(w['pid'])
    assert all(len(pids)==1 for pids in workers.values()),'Worker was not reused'
    assert len(set.union(*workers.values()))==len(workers),'Stage/profile processes were mixed'
    for kind in sorted({t['validationCase'].rsplit('-',1)[0] for t in new}):
        left=[t['elapsedSeconds'] for t in old if t['validationCase'].startswith(kind+'-')];right=[t['elapsedSeconds'] for t in new if t['validationCase'].startswith(kind+'-')]
        summary[kind]={'old':left,'new':right,'oldMedian':statistics.median(left),'newMedian':statistics.median(right),'reductionPercent':round((1-statistics.median(right)/statistics.median(left))*100,1)}
    result={'status':'PASS','comparisons':matched,'timings':summary,'warmup':json.loads((a.candidate/'warmup.json').read_text(encoding='utf8'))}
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
