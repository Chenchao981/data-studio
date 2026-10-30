// Actual frozen Windows client through its temporary, loopback-only Qt CDP port.
// Seed a private workspace with a completed real task before running.
// Inputs are intentionally cleared at each application startup.
// Usage from repository root: node apps/web/tests/verify-bundle-ui.mjs <exe> <private-home-with-one-successful-Jiemin-DVDS> <evidence-directory>
import {spawn,execFile} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';

if(process.argv.length!==5)throw Error('Usage: node apps/web/tests/verify-bundle-ui.mjs <exe> <private-home-with-one-successful-Jiemin-DVDS> <new-evidence-directory>');
const [exe,home,output]=process.argv.slice(2).map(p=>path.resolve(p));
await mkdir(output,{recursive:true});
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const reserve=net.createServer();await new Promise(resolve=>reserve.listen(0,'127.0.0.1',resolve));
const port=reserve.address().port;await new Promise(resolve=>reserve.close(resolve));
const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>! /^(PYTHON|CONDA|QT)/.test(key)));
env.PATH=process.env.SystemRoot+'\\System32;'+process.env.SystemRoot;
env.QTWEBENGINE_REMOTE_DEBUGGING='127.0.0.1:'+port;
const proc=spawn(exe,['--home',home],{env,windowsHide:false,stdio:'ignore'});
let socket,sequence=0;const pending=new Map(),errors=[];
async function send(method,params={}){
 const id=++sequence;
 return await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
}
async function evaluate(expression){
 const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
 if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;
}
async function wait(expression,timeout=30000){
 const deadline=Date.now()+timeout;
 while(Date.now()<deadline){if(await evaluate(expression))return;await pause(150);}
 throw Error('UI timeout: '+expression);
}
async function click(selector){await wait(`!!document.querySelector(${JSON.stringify(selector)})`);await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'nearest'})`);await pause(50);await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);await pause(100);}
async function button(text){const q=`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`;await wait(`!!(${q})`);await evaluate(`(${q}).click()`);await pause(100);}
async function screenshot(name){const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));}
const escape=`document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`;
try{
 let target;const deadline=Date.now()+60000;
 while(Date.now()<deadline){try{const rows=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();target=rows.find(p=>p.type==='page'&&p.url.startsWith('studio:'));if(target)break;}catch{}await pause(200);}
 if(!target)throw Error('No local Studio CDP page');
 socket=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
 socket.onmessage=event=>{const r=JSON.parse(event.data);if(r.method==='Runtime.exceptionThrown')errors.push(r.params.exceptionDetails);if(!r.id)return;const p=pending.get(r.id);if(!p)return;pending.delete(r.id);clearTimeout(p.timer);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result);};
 await send('Runtime.enable');await send('Page.enable');
 await wait(`!!document.querySelector('#input-paths')`);
 if(await evaluate(`document.documentElement.dataset.theme==='dark'`))await click('button[title="切换明暗主题"]');
 await evaluate(`(()=>{window.resultCalls=[];const transport=window.qt.webChannelTransport;const original=transport.send.bind(transport);transport.send=(raw)=>{try{const m=JSON.parse(raw);if(m.args&&typeof m.args[1]==='string')window.resultCalls.push(m.args[1]);}catch{}return original(raw);};})()`);
 const paths=await evaluate(`({input:document.querySelector('#input-paths')?.value,output:document.querySelector('#output-directory')?.value,unified:[...document.querySelectorAll('button')].filter(b=>b.textContent.trim()==='选择数据源').length})`);
 if(await evaluate(`document.body.innerText.includes('演示')||document.body.innerText.includes('真实分析结果')`))throw Error('Demo controls remain');
 if(paths.input)throw Error('Input list was restored at startup');
 if(paths.unified!==1||!paths.output)throw Error('Missing unified path controls');
 await wait(`!!document.querySelector('[aria-label=其他分析操作] .operation-card')`);
 await screenshot('packaged-paths');
 if(await evaluate(`!!document.querySelector('.content [data-stage]')`))throw Error('Stage cards still occupy main workspace');
 await click('[data-stage=FT]');
 await evaluate(`(()=>{const e=document.querySelector('input[aria-label="搜索工厂"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'shjm');e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await wait(`document.querySelectorAll('.factory-tile').length===1 && !!document.querySelector('[data-factory=JIEMIN]')`);
 await click('[data-factory=JIEMIN]');
 await evaluate(`(()=>{const e=document.querySelector('input[aria-label="搜索工厂"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'__none__');e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await wait(`!!document.querySelector('.factory-no-match')`);
 if(!await evaluate(`document.querySelector('.factory-current strong').textContent==='上海捷敏'`))throw Error('Search changed selected factory');
 await click('[aria-label="清空工厂搜索"]');
 await wait(`document.querySelectorAll('.factory-tile').length===6`);
 await screenshot('factory-cards-ft');
 const menus={DIANJI:['FT-ALL','电基PAT统计','SBL / SYL'],JIEQUN:['DC-AI（自动识别）','DVDS','RG','杰群PAT统计','SBL / SYL'],RIYUEXIN:['DC','DVDS','RG','日月新PAT统计','SBL / SYL'],JIEMIN:['DC','DVDS','RG','上海捷敏PAT统计'],JIJIA:['FT-ALL'],RIYUEGUANG:['数据清洗','日月光PAT统计']};
 for(const [factory,expected] of Object.entries(menus)){
  await click(`[data-factory=${factory}]`);
  const actual=await evaluate(`[...document.querySelectorAll('.chooser-operation .operation-card')].map(b=>b.textContent.trim())`);
  if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(factory+' routes differ: '+JSON.stringify(actual));
  if(await evaluate(`!!document.querySelector('.more-operations')`))throw Error('FT operations must be directly visible');
  const codes=await evaluate(`[...document.querySelectorAll('.chooser-operation .operation-card')].map(b=>b.dataset.tool)`);
  for(const code of codes){await click(`[data-tool="${code}"]`);if(!await evaluate(`document.querySelector('[data-tool="${code}"]').getAttribute('aria-pressed')==='true'`))throw Error('Operation selection failed');}
 }
 await click('[data-factory=DIANJI]');
 if(await evaluate(`!!document.querySelector('.chooser-operation [data-tool*=CHART], [data-tool*=CLEANED_PAT]')`))throw Error('Extra controls in main operations');
 await click('.chooser-charts .operation-card');await screenshot('dianji-separate-charts');
 await click('[data-tool=LOCAL_FT_DIANJI_RAW_PAT_V1]');await screenshot('dianji-main-operations');
 await click('[data-stage=CP]');await click('[data-factory=JETECH]');
 if(!await evaluate(`document.querySelector('[data-factory=JETECH]').textContent.includes('佳泰') && !document.querySelector('.workflow-config').textContent.includes('积塔')`))throw Error('JETECH must display 佳泰');
 await click('[data-stage=FT]');
 if(!await evaluate(`document.querySelector('[data-tool=LOCAL_FT_DIANJI_RAW_PAT_V1]')?.getAttribute('aria-pressed')==='true'`))throw Error('FT operation was lost on workspace switch');
 await click('[data-stage=CP]');
 if(!await evaluate(`document.querySelector('[data-factory=JETECH]')?.getAttribute('aria-pressed')==='true'`))throw Error('CP factory was lost on workspace switch');
 await screenshot('cp-workbench');
 await click('[data-stage=FT]');await screenshot('ft-workbench');
 if(await evaluate(`document.body.innerText.includes('任务进度')`))throw Error('Removed progress navigation remains');
 await wait(`!!document.querySelector('.task-log')`);
 await button('历史记录');
 const dvdsHistory=`[...document.querySelectorAll('.history-list article')].filter(a=>a.textContent.includes('上海捷敏')&&a.textContent.includes('DVDS'))`;
 const realResult=`(${dvdsHistory}).flatMap(a=>[...a.querySelectorAll('button')]).find(b=>b.textContent.trim()==='查看结果')`;
 await wait(`!!(${realResult})`);
 if(await evaluate(`(${dvdsHistory}).length`)!==1)throw Error('Seed exactly one successful Jiemin DVDS task in this private home');
 // Measure UI stalls during the real workload separately from engine duration.
 const workloadStarted=Date.now();
 await evaluate(`window.workloadDelays=[];window.workloadTasks=[];window.workloadLast=performance.now();window.workloadTimer=setInterval(()=>{const n=performance.now();if(workloadDelays.length<10000)workloadDelays.push(Math.max(0,n-workloadLast-100));workloadLast=n;},100);window.workloadObserver=new PerformanceObserver(list=>{for(const e of list.getEntries())if(workloadTasks.length<2000)workloadTasks.push(e.duration)});workloadObserver.observe({type:'longtask'});`);
 // Re-run the single, previously verified real DVDS sample in the isolated home.
 await evaluate(`[...(${dvdsHistory})[0].querySelectorAll('button')].find(b=>b.textContent.trim()==='重新执行').click()`);
 await wait(`!!document.querySelector('.task-log')`);
 await wait(`!!document.querySelector('.clean-launch')`);
 await wait(`document.querySelector('.log-stream')?.textContent.includes('上海捷敏 DVDS：读取')`,120000);
 await screenshot('packaged-live-log');
 await wait(`document.querySelector('.task-log .log-state')?.textContent==='已完成'`,240000);
 await wait(`document.querySelector('.log-stream')?.textContent.includes('上海捷敏 DVDS 完成')`);
 await evaluate(`(()=>{const log=document.querySelector('.log-stream');log.style.height='45px';log.scrollTop=0;log.dispatchEvent(new Event('scroll',{bubbles:true}));})()`);
 await wait(`[...document.querySelectorAll('.task-log button')].some(b=>b.textContent==='回到最新')`);
 await button('回到最新');
 await wait(`(()=>{const e=document.querySelector('.log-stream');return e.scrollHeight-e.scrollTop-e.clientHeight<24;})()`);
 await evaluate(`document.querySelector('.log-stream').style.height=''`);
 if(await evaluate(`document.querySelector('.log-stream').textContent.length>60000`))throw Error('Log buffer exceeded bound');
 await screenshot('packaged-completed-log');
 const workload=await evaluate(`(()=>{clearInterval(workloadTimer);workloadObserver.disconnect();const sorted=[...workloadDelays].sort((a,b)=>a-b);return {timerDelayP95Ms:sorted[Math.ceil(sorted.length*.95)-1],maxTimerDelayMs:Math.max(...sorted),samples:sorted.length,longTasks:workloadTasks};})()`);workload.elapsedMs=Date.now()-workloadStarted;
 if(workload.timerDelayP95Ms>200)throw Error('UI stalls during real cleaning: '+JSON.stringify(workload));
 await button('已完成');
 await wait(`!!(${realResult})`);await evaluate(`(${realResult}).click()`);await wait(`!!document.querySelector('.result-directory')`,60000);
 if(await evaluate(`!!document.querySelector('.ag-root, .preview-panel, .artifact-list')`))throw Error('Result preview is still mounted');
 await click('button[aria-label="选择分析任务"]');await wait(`!!document.querySelector('[role=listbox]')`);
 await evaluate(`(()=>{const input=document.querySelector('input[aria-label="搜索选择分析任务"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'__no_matching_task__');input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await pause(150);await wait(`document.querySelector('.picker-empty')?.textContent==='没有匹配项'`);
 await evaluate(escape);await wait(`!document.querySelector('[role=listbox]')`);await screenshot('packaged-result');
 await evaluate(`document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))`);await wait(`!!document.querySelector('[role=listbox]')`);
 await evaluate(`document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))`);
 await wait(`document.activeElement===[...document.querySelectorAll('[role=option]')].at(-1)`);await evaluate(escape);
 const popupTiming=await evaluate(`(async()=>{
   const timings=[];for(let i=0;i<20;i++){
     const start=performance.now();document.querySelector('button[aria-label="选择分析任务"]').click();
     await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
     timings.push(performance.now()-start);${escape};await new Promise(r=>requestAnimationFrame(r));
   }return timings;
 })()`);
 await click('button[aria-label="选择分析任务"]');await wait(`!!document.querySelector('[role=listbox]')`);
 const bounds=await evaluate(`(()=>{const r=document.querySelector('.picker-popover').getBoundingClientRect();const c=document.querySelector('.content-shell').getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:innerHeight,visibleTop:Math.max(0,c.top),visibleBottom:Math.min(innerHeight,c.bottom)};})()`);
 if(bounds.top<bounds.visibleTop||bounds.bottom>bounds.visibleBottom)throw Error('Picker clipped: '+JSON.stringify(bounds));
 await screenshot('packaged-picker');await evaluate(escape);
 await click('button[title="切换明暗主题"]');await wait(`document.documentElement.dataset.theme==='dark'`);await screenshot('packaged-dark');
 const responsive=[];
 for(const [width,height] of [[1000,760],[920,620]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await pause(300);
  await click('button[aria-label="选择分析任务"]');
  const bounds=await evaluate(`(()=>{const r=document.querySelector('.picker-popover').getBoundingClientRect();const c=document.querySelector('.content-shell').getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:innerHeight,visibleTop:Math.max(0,c.top),visibleBottom:Math.min(innerHeight,c.bottom)};})()`);
  if(bounds.top<bounds.visibleTop||bounds.bottom>bounds.visibleBottom)throw Error('Small-window picker clipped: '+JSON.stringify(bounds));
  responsive.push({width,height,...bounds});await screenshot('picker-'+width);await evaluate(escape);
 }
 await click('[data-stage=CP]');
 await wait(`!!document.querySelector('#input-paths')`);
 if(!(await evaluate(`document.documentElement.scrollWidth<=innerWidth`)))throw Error('Workspace horizontal overflow');
 await evaluate(`document.querySelector('.path-controls').scrollIntoView({block:'start'})`);await pause(150);
 await screenshot('packaged-paths-small-dark');
 await button('设置');await wait(`[...document.querySelectorAll('button')].some(b=>b.textContent.includes('更改输出目录'))`);
 const outputControl=await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('更改输出目录'));b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})()`);
 if(!outputControl)throw Error('Output directory setting clipped');await screenshot('settings-small-dark');
 await send('Emulation.clearDeviceMetricsOverride');
 if(errors.length)throw Error(JSON.stringify(errors));
 const resultCalls=await evaluate('window.resultCalls');if(resultCalls.includes('getPreview'))throw Error('Unexpected preview request');
 const eagerDemoResources=await evaluate(`performance.getEntriesByType('resource').map(r=>r.name).filter(n=>n.includes('/Preview-')||n.includes('/Analysis-'))`);if(eagerDemoResources.length)throw Error('Demo modules loaded eagerly');
 await writeFile(path.join(output,'evidence.json'),JSON.stringify({status:'PASS',exe,workload,resultCalls,paths,uiErrors:errors,popupTiming,pickerBounds:bounds,responsive,checks:['Frozen EXE using isolated PATH','Existing real history reopened','Folder-only result overview','Searchable task picker, ArrowUp and Escape','Dark theme'],versionText:await evaluate(`document.querySelector('.version').textContent`)},null,2));
 console.log('PASS: frozen client workflow and result picker');
}catch(error){
 await writeFile(path.join(output,'failure.txt'),String(error)+'\n'+(socket?await evaluate(`document.querySelector('.task-log')?.outerHTML`):''));
 if(socket)await screenshot('failure');
 throw error;
}finally{
 socket?.close();for(const p of pending.values())clearTimeout(p.timer);
 await writeFile(path.join(output,'pid.txt'),String(proc.pid));
 // WM_CLOSE only to the exact validation process started by this test.
 const command=`$p=Get-Process -Id ${proc.pid} -ErrorAction SilentlyContinue; if($p -and $p.Path -eq '${exe.replaceAll("'","''")}'){ $null=$p.CloseMainWindow() }`;
 await new Promise(resolve=>execFile('powershell.exe',['-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',command],{windowsHide:true},()=>resolve()));
 proc.unref();
}
