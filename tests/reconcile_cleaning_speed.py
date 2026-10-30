"""Reconcile repeated cleaning runs against original-engine reference outputs."""
import argparse,csv,hashlib,json,re,statistics,zipfile
from pathlib import Path

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def key(p):
 name=re.sub(r'\d{8}_?\d{6}', '<time>',p.name)
 return name

def compare(expected,actual):
 left={key(p):p for p in expected};right={key(p):p for p in actual};assert left.keys()==right.keys(),(list(left),list(right));cells=0
 for name,a in left.items():
  b=right[name]
  if a.suffix=='.xlsx':
   with zipfile.ZipFile(a) as x,zipfile.ZipFile(b) as y:
    names={n for n in x.namelist() if n.startswith('xl/')};assert names=={n for n in y.namelist() if n.startswith('xl/')}
    for n in names:assert x.read(n)==y.read(n),(name,n)
    cells+=len(names)
  else:
   with a.open(encoding='utf-8-sig',newline='') as x,b.open(encoding='utf-8-sig',newline='') as y:
    rows=list(csv.reader(x));other=list(csv.reader(y));assert rows==other,name;cells+=sum(map(len,rows))
 return cells

def main():
 p=argparse.ArgumentParser();p.add_argument('evidence',type=Path);p.add_argument('--candidate',default='optimized');p.add_argument('--direct',default='direct');args=p.parse_args();r=args.evidence
 base=json.loads((r/'baseline-v2/validation.json').read_text(encoding='utf8'));new=json.loads((r/args.candidate/'validation.json').read_text(encoding='utf8'));direct=json.loads((r/(args.direct+'.json')).read_text())
 matched=[]
 for old,task in zip(base,new):
  name=task['validationCase'];assert name==old['validationCase']
  reference=[p for p in (r/args.direct/name/'stage/files').rglob('*') if p.suffix in {'.csv','.xlsx'}]
  actual=[Path(a['path']) for a in task['artifacts'] if a['name'].startswith('files/') and Path(a['path']).suffix in {'.csv','.xlsx'}]
  previous=[Path(a['path']) for a in old['artifacts'] if a['name'].startswith('files/') and Path(a['path']).suffix in {'.csv','.xlsx'}]
  count=compare(reference,actual);assert count==compare(reference,previous)
  for home,t in [('baseline-v2',old),(args.candidate,task)]:
   receipt=json.loads((r/home/'results'/t['id']/'receipt.json').read_text(encoding='utf8'))
   if home=='baseline-v2':identity=receipt['result']['business_identity']
   else:assert receipt['result']['business_identity']==identity
   for a in t['artifacts']:assert digest(Path(a['path']))==a['sha256']
   for path,sha in receipt['selectedOriginals'].items():assert digest(Path(path))==sha
  matched.append(dict(case=name,status='PASS',csvCellsOrExactXlsxParts=count,seconds=task['validationSeconds'],phases=task.get('transportTiming'),inner=receipt['result'].get('timing_seconds')))
 summary={}
 for stage in ('cp','ft'):
  times=lambda rows: [t['validationSeconds'] for t in rows if t['validationCase'].startswith(stage)]
  a=times(base);b=times(new);d=[t['seconds'] for t in direct if t['name'].startswith(stage)]
  summary[stage]=dict(baseline=a,optimized=b,direct=d,baselineMedian=statistics.median(a),optimizedMedian=statistics.median(b),directMedian=statistics.median(d),improvement=1-statistics.median(b)/statistics.median(a))
 result=dict(status='PASS',comparisons=matched,timings=summary)
 (r/('reconciliation-'+args.candidate+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
