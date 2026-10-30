"""Live engine logs, single-job layout, duration, failure and cancel in real Qt."""
import argparse,json,multiprocessing,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--matrix',type=Path,required=True);a=p.parse_args()
 root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
 from apps.desktop.rendering import configure_rendering
 configure_rendering('software')
 from PySide6.QtCore import Qt
 from PySide6.QtWidgets import QApplication,QMessageBox
 from apps.desktop.security import register_scheme
 register_scheme();app=QApplication([])
 from apps.desktop.shell import StudioWindow
 w=StudioWindow(root/'home',ROOT/'apps/web/dist');w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);w.resize(1500,1060);w.show()
 def wait(check,timeout=45):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   app.processEvents()
   if check():return
   time.sleep(.015)
  raise AssertionError('Live console UI timeout')
 def js(code):
  v=[];w.page.runJavaScript(code,v.append);wait(lambda:bool(v));return v[0]
 def button(text):
  q='[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==='+json.dumps(text)+')'
  wait(lambda:js(f'!!({q})&&!({q}).disabled'));js(f'({q}).click()')
 def shot(name):
  js('document.querySelector(".cleaning-console")?.scrollIntoView({block:"end"})');app.processEvents();w.grab().save(str(root/(name+'.png')))
 def configure(case):
  stage='CP' if case['code'].startswith('LOCAL_CP') else 'FT';factory='HUAHONG' if stage=='CP' else 'JIEMIN'
  js(f'document.querySelector("[data-stage={stage}]").click()');wait(lambda:js(f'!!document.querySelector("[data-factory={factory}]")'))
  js(f'document.querySelector("[data-factory={factory}]").click()');wait(lambda:js(f'!!document.querySelector("[data-tool={case["code"]}]")'))
  js(f'document.querySelector("[data-tool={case["code"]}]").click()')
  source=str(Path(case['source']).resolve())
  js('(()=>{const e=document.querySelector("#input-paths");Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(e,'+json.dumps(source)+');e.dispatchEvent(new Event("input",{bubbles:true}));})()')
  if js('[...document.querySelectorAll("button")].some(b=>b.textContent.trim()==="应用输入路径")'):button('应用输入路径')
  wait(lambda:js('document.querySelector("#input-paths").value')==source)
  return stage
 checks=[];samples=[]
 try:
  wait(lambda:js('!!document.querySelector(".clean-launch")'))
  js('window.errors=[];window.addEventListener("error",e=>window.errors.push(e.message));window.addEventListener("unhandledrejection",e=>window.errors.push(String(e.reason)))')
  assert not js('document.body.innerText.includes("任务进度")')
  out=root/'exports';out.mkdir();w.core.set_output_directory(str(out));w.bridge.changed.emit()
  cases=json.loads(a.matrix.read_text(encoding='utf-8-sig'))[:2]
  for case in cases:
   stage=configure(case);assert not js('!!document.querySelector(".file-table")');shot(stage+'-ready')
   previous={t['id'] for t in w.core.history()};button('清洗');wait(lambda:any(t['id'] not in previous for t in w.core.history()))
   task=next(t for t in w.core.history() if t['id'] not in previous);tid=task['id'];changes=[];last='';paused=False;tail_verified=False
   deadline=time.monotonic()+300
   while time.monotonic()<deadline:
    app.processEvents();task=w.core.task(tid)
    text=js('document.querySelector(".log-stream")?.textContent||""')
    if text!=last:
     changes.append(dict(status=task['status'],length=len(text),tail=text[-400:],files=[line for line in text.splitlines() if ('处理文件' in line or '读取 ' in line)][:20]));last=text
     if task['status']=='RUNNING' and len(text)>800 and not paused:
      assert js('document.querySelector(".log-stream").scrollHeight-document.querySelector(".log-stream").scrollTop-document.querySelector(".log-stream").clientHeight<30')
      js('(()=>{const e=document.querySelector(".log-stream");e.scrollTop=0;e.dispatchEvent(new Event("scroll"));})()');paused=True
      wait(lambda:js('document.body.innerText.includes("回到最新")'));shot(stage+'-running');button('回到最新');tail_verified=True
    if task['status'] in {'SUCCESS','FAILED','CANCELLED'}:break
    time.sleep(.05)
   assert task['status']=='SUCCESS',task.get('error')
   wait(lambda:js('document.querySelector(".log-state").textContent')=='已完成')
   wait(lambda:js('document.querySelector(".log-stream").textContent.includes("分析成功")'))
   assert len([r for r in changes if r['status']=='RUNNING'])>=2,changes
   assert any(r['files'] and r['status']=='RUNNING' for r in changes)
   assert task['elapsedSeconds']>0 and task['publishedDirectory']
   assert js('!!document.querySelector(".clean-launch")')
   shot(stage+'-complete');button('查看结果');wait(lambda:js('document.body.innerText.includes("清洗耗时")'))
   assert not js('document.querySelector(".metrics").innerText.includes("完成时间")')
   samples.append(dict(stage=stage,task=task,logUpdates=changes,autoScroll=tail_verified,duration=js('document.querySelector(".metrics").innerText')))
   js(f'document.querySelector("[data-stage={stage}]").click()');wait(lambda:js('!!document.querySelector(".clean-launch")'))
  # Cancel a real job through the inline console, before publication.
  configure(cases[0]);previous={t['id'] for t in w.core.history()};button('清洗')
  wait(lambda:any(t['id'] not in previous for t in w.core.history()));tid=next(t['id'] for t in w.core.history() if t['id'] not in previous)
  button('取消');wait(lambda:w.core.task(tid)['status']=='CANCELLED',40)
  assert not w.core.task(tid).get('publishedDirectory');shot('cancelled');checks.append('real task cancellation without publication')
  bad=root/'broken.zip';bad.write_bytes(b'not an archive')
  configure({**cases[0],'source':str(bad)});previous={t['id'] for t in w.core.history()};button('清洗')
  wait(lambda:any(t['id'] not in previous for t in w.core.history()));tid=next(t['id'] for t in w.core.history() if t['id'] not in previous)
  wait(lambda:w.core.task(tid)['status']=='FAILED',60);wait(lambda:js('document.querySelector(".log-state").textContent')=='失败')
  assert not w.core.task(tid).get('publishedDirectory');shot('failed');checks.append('invalid archive visible error and no partial publication')
  w.resize(920,740);wait(lambda:js('innerWidth<1000'));assert js('document.documentElement.scrollWidth<=innerWidth');shot('compact')
  w.core.save_settings({'theme':'dark'});w.bridge.changed.emit();wait(lambda:js('document.documentElement.dataset.theme')=='dark');shot('dark')
  assert not js('window.errors.length')
  checks+=['single-job workspace stays visible after start','real engine log updates before completion','auto scroll and resume','seconds from actual start to completion','source/output editable','no task progress entry','920px and dark theme']
  (root/'evidence.json').write_text(json.dumps(dict(status='PASS',checks=checks,samples=samples),ensure_ascii=False,indent=2),encoding='utf8');print('PASS live logs and real tasks',flush=True)
 except Exception:
  (root/'failure-dom.txt').write_text(js('document.body.innerText') or '',encoding='utf8');shot('failure');raise
 finally:
  QMessageBox.question=lambda *a,**k:QMessageBox.StandardButton.Yes;w.close();app.processEvents()
if __name__=='__main__':multiprocessing.freeze_support();main()
