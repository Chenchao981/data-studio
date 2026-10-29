// Run from apps/web. Only the test child receives a loopback debugging port.
import {spawn,execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
const root=path.resolve('../..');
const output=path.join(root,'artifacts','package-'+Date.now());fs.mkdirSync(output,{recursive:true});
const realSource=process.argv[2];
const toolCode=process.argv[3]||'LOCAL_CP_HUAHONG_TD_V1';
const stage=toolCode.split('_')[1];const factory=toolCode.split('_')[2];
if(!realSource)throw Error('Pass a private sample directory, optionally followed by a LOCAL tool code');
execFileSync(path.join(root,'.venv-cpython/Scripts/python.exe'),['-X','utf8','-c',
  'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from python_core.core import Core;Core(Path(sys.argv[2])).register([sys.argv[3]])',
  root,path.join(output,'workspace'),path.resolve(realSource)]);
const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
const env={...process.env};
for(const k of Object.keys(env))if(/^(PATH|PYTHONHOME|PYTHONPATH|QT_PLUGIN_PATH|QML2_IMPORT_PATH|CONDA_PREFIX|QTWEBENGINE_REMOTE_DEBUGGING)$/i.test(k))delete env[k];
env.PATH=process.env.SystemRoot+'\\System32';env.QTWEBENGINE_REMOTE_DEBUGGING=`127.0.0.1:${port}`;
const child=spawn(path.join(root,'dist/DesktopDataStudio/DesktopDataStudio.exe'),['--home',path.join(output,'workspace')],{env,windowsHide:true,stdio:'ignore'});
const exited=new Promise(r=>child.once('exit',code=>r(code)));
let socket;
try{
  let ready=false;
  for(let i=0;i<100;i++){try{const response=await fetch(`http://127.0.0.1:${port}/json/version`);if(response.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,150));}
  if(!ready)throw Error('Packaged Qt debug endpoint did not start');
  const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let serial=0;const pending=new Map();const errors=[];
  socket.onmessage=event=>{const message=JSON.parse(event.data);if(message.method==='Runtime.exceptionThrown')errors.push(JSON.stringify(message.params));const p=pending.get(message.id);if(p){pending.delete(message.id);clearTimeout(p.timer);message.error?p.reject(Error(message.error.message)):p.resolve(message.result);}};
  const cdp=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},10000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  await cdp('Runtime.enable');
  const js=async expression=>{const r=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const wait=async(expression,seconds=15)=>{for(let i=0;i<seconds*10;i++){if(await js(expression))return;await new Promise(r=>setTimeout(r,100));}throw Error('UI condition timed out: '+expression);};
  const click=label=>js(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)}||b.getAttribute('title')===${JSON.stringify(label)}||b.getAttribute('aria-label')===${JSON.stringify(label)})?.click()`);
  const screenshot=async name=>{await new Promise(r=>setTimeout(r,500));const r=await cdp('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name),Buffer.from(r.data,'base64'));};
  await wait("Boolean(document.querySelector('.file-table'))");
  await js(`document.querySelector('[data-stage="${stage}"]').click()`);
  await wait(`!!document.querySelector('[data-factory="${factory}"]')`);
  await js(`document.querySelector('[data-factory="${factory}"]').click()`);
  if(!await js(`!!document.querySelector('[data-tool="${toolCode}"]')`))await js("document.querySelector('.more-operations').click()");
  await wait(`!!document.querySelector('[data-tool="${toolCode}"]')`);
  await js(`document.querySelector('[data-tool="${toolCode}"]').click()`);
  await js(`document.querySelector('input[aria-label="选择本页输入"]').click()`);
  if(!await js("Boolean(document.querySelector('.operation-card.selected'))"))throw Error('Rule not selected');
  await screenshot('workspace.png');
  await click('开始清洗');
  await wait("!!document.querySelector('.history-list .status-SUCCESS,.history-list .status-FAILED')",600);
  if(!await js("!!document.querySelector('.history-list .status-SUCCESS')"))throw Error(await js('document.body.innerText'));
  await screenshot('real-history.png');await click('查看结果');
  await wait("document.querySelectorAll('.ag-row').length>0");await screenshot('real-result.png');
  if(await js("document.body.innerText.includes('DEMO-IGBT')"))throw Error('Real result showed demo data');
  const realCheck=execFileSync(path.join(root,'.venv-cpython/Scripts/python.exe'),['-X','utf8','-c',
    'import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from python_core.core import Core;c=Core(Path(sys.argv[2]));t=c.history()[0];assert t["status"]=="SUCCESS" and not t["demo"];c.output(t["id"]);assert t["tables"] and not t.get("warning");print(json.dumps({k:t[k] for k in ["id","status","receipt"]}))',
    root,path.join(output,'workspace')],{encoding:'utf8'});
  fs.writeFileSync(path.join(output,'real-result.json'),realCheck);
  await click('清洗工作台');await click('查看演示数据');
  await js("document.querySelector('input[aria-label=\"选择本页输入\"]').click()");
  await click('运行示例');
  await wait("!!document.querySelector('.history-list .status-SUCCESS')&&document.body.innerText.includes('模拟格式冲突')&&!document.querySelector('.history-list .status-RUNNING,.history-list .status-QUEUED')");
  await screenshot('history.png');await click('清洗结果');await click('演示数据');await click('演示表格');
  await wait("document.querySelector('.ag-center-cols-container')?.innerText.includes('DEMO-IGBT')");
  await screenshot('preview.png');await click('演示统计');
  await wait("document.querySelectorAll('canvas').length>=2");
  await screenshot('analysis.png');await click('切换明暗主题');
  await wait("document.documentElement.dataset.theme==='dark'");
  await screenshot('analysis-dark.png');
  if(errors.length)throw Error(errors.join('\n'));
  const modules=execFileSync('powershell.exe',['-NoProfile','-Command',`(Get-Process -Id ${child.pid}).Modules | ForEach-Object { $_.FileName }`],{encoding:'utf8'});
  if(/anaconda|\.venv|\.runtime/i.test(modules))throw Error('Development runtime leaked into packaged process');
  fs.writeFileSync(path.join(output,'loaded-modules.txt'),modules);
  fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify({status:'PASS',pid:child.pid,toolCode,checks:['Packaged EXE with Windows-only PATH','Actual Qt React UI and QWebChannel','Real analysis through bundled CPython and engine kit','Original result worksheet preview and persisted output hash','Frozen multiprocessing success and failure','100k demo preview, ECharts, dark theme','No Anaconda/venv/runtime modules loaded']},null,2));
  console.log('PASS packaged application:',output);
}catch(error){
  console.error('Package test failed:',error);
  const dialogs=execFileSync(path.join(root,'.venv-cpython/Scripts/python.exe'),['-X','utf8','-c',`import win32gui,win32process\ndef show(h,_):\n if win32process.GetWindowThreadProcessId(h)[1]==${child.pid}:\n  print('WINDOW',win32gui.GetWindowText(h))\n  win32gui.EnumChildWindows(h,lambda c,_: print(win32gui.GetWindowText(c)),None)\n return True\nwin32gui.EnumWindows(show,None)`],{encoding:'utf8'});
  console.error(dialogs);throw error;
}finally{
  socket?.close();
  execFileSync(path.join(root,'.venv-cpython/Scripts/python.exe'),['-c',`import win32gui,win32process,win32con; win32gui.EnumWindows(lambda h,_: win32gui.PostMessage(h,win32con.WM_CLOSE,0,0) if win32process.GetWindowThreadProcessId(h)[1]==${child.pid} and win32gui.GetWindowText(h).startswith('Desktop Data Studio') else None, None)`]);
  const code=await Promise.race([exited,new Promise(r=>setTimeout(()=>r('timeout'),10000))]);
  if(code==='timeout'){child.kill();throw Error('Packaged application required forced cleanup');}
  if(code!==0)throw Error('Packaged application exit code '+code);
  console.log('PASS normal packaged exit');
}
