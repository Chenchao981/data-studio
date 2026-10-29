// Frozen-client lab benchmark. Two-rAF response is a proxy, NOT field INP.
// Usage: node measure-ui-performance.mjs <exe> <isolated-output-directory> [--strict]
// GUI must be visible: a hidden window distorts frame pacing and cannot close normally.
import {spawn,execFile} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
const [exe,output]=process.argv.slice(2).map(p=>path.resolve(p));
await mkdir(output,{recursive:true});
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const stats=values=>{const a=[...values].sort((x,y)=>x-y);return {count:a.length,median:a[Math.floor(a.length/2)],p95:a[Math.ceil(a.length*.95)-1],max:a.at(-1)};};
const startup=[],evidence={exe,metric:'scripted action to DOM confirmation and two animation frames; not INP',startupMs:startup,runs:[]};
for(let run=0;run<3;run++){
 const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
 const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>! /^(PYTHON|CONDA|QT)/.test(k)));
 env.PATH=process.env.SystemRoot+'\\System32;'+process.env.SystemRoot;env.QTWEBENGINE_REMOTE_DEBUGGING='127.0.0.1:'+port;
 const start=performance.now(),proc=spawn(exe,['--home',path.join(output,'home')],{env,windowsHide:false,stdio:'ignore'});
 let ws,id=0;const pending=new Map(),errors=[];
 function send(method,params={}){return new Promise((resolve,reject)=>{const key=++id,timer=setTimeout(()=>{pending.delete(key);reject(Error('CDP timeout: '+method));},30000);pending.set(key,{resolve,reject,timer});ws.send(JSON.stringify({id:key,method,params}));});}
 async function js(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
 async function wait(expression){const until=Date.now()+45000;while(Date.now()<until){if(await js(expression))return;await pause(30);}throw Error('Timed out: '+expression);}
 try{
  let target;const until=Date.now()+45000;while(Date.now()<until){try{target=(await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p=>p.url.startsWith('studio:'));if(target)break;}catch{}await pause(50);}
  if(!target)throw Error('No page');
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.method==='Runtime.exceptionThrown')errors.push(r.params);if(!r.id)return;const p=pending.get(r.id);if(!p)return;pending.delete(r.id);clearTimeout(p.timer);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result);};
  await send('Runtime.enable');await send('Performance.enable');await wait(`!!document.querySelector('#input-paths')`);startup.push(performance.now()-start);
  await js(`window.perfLong=[];window.perfObserver=new PerformanceObserver(list=>{for(const e of list.getEntries())if(perfLong.length<2000)perfLong.push(e.duration)});perfObserver.observe({type:'longtask'});window.perfPaint=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));`);
  await send('HeapProfiler.collectGarbage');const before=(await send('Performance.getMetrics')).metrics;
  const actions=await js(`(async()=>{
    const stage=[],factory=[],search=[];
    for(let i=0;i<60;i++){
      let start=performance.now();const s=i%2?'CP':'FT';document.querySelector('[data-stage='+s+']').click();await perfPaint();
      if(document.querySelector('[data-stage='+s+']').getAttribute('aria-pressed')!=='true')throw Error('Stage selection');stage.push(performance.now()-start);
      const all=[...document.querySelectorAll('[data-factory]')],button=all[Math.floor(i/2)%all.length];start=performance.now();button.click();await perfPaint();
      if(button.getAttribute('aria-pressed')!=='true')throw Error('Factory selection');factory.push(performance.now()-start);
    }
    const input=document.querySelector('[aria-label=搜索工厂]');if(input){for(let i=0;i<60;i++){
        for(const value of ['__none__','']){const start=performance.now();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));await perfPaint();
          if(value&&!document.querySelector('.factory-no-match'))throw Error('Search no match');if(!value&&!document.querySelector('[data-factory]'))throw Error('Search clear');search.push(performance.now()-start);
        }
      }
    }return {stage,factory,search};
  })()`);
  await send('HeapProfiler.collectGarbage');const after=(await send('Performance.getMetrics')).metrics;
  const idleBefore=Object.fromEntries(after.map(m=>[m.name,m.value]));await pause(6000);const idleAfter=Object.fromEntries((await send('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]));
  const info={run,pageState:await js('({visible:document.visibilityState,focused:document.hasFocus()})'),actions:Object.fromEntries(Object.entries(actions).filter(([,v])=>v.length).map(([k,v])=>[k,stats(v)])),before,after,idleRendererMainThreadPercent:100*(idleAfter.TaskDuration-idleBefore.TaskDuration)/(idleAfter.Timestamp-idleBefore.Timestamp),longTasks:await js('perfLong'),errors,rawActions:actions};
  evidence.runs.push(info);
  if(errors.length)throw Error('Frontend exceptions');
  info.withinInteractionBudget=Object.values(info.actions).every(v=>v.p95<=200);
  console.log(JSON.stringify({run,startupMs:startup.at(-1),actions:info.actions,idleRendererMainThreadPercent:info.idleRendererMainThreadPercent}));
 }catch(e){evidence.error=String(e);throw e;}
 finally{
  evidence.startupSummary=stats(startup);await writeFile(path.join(output,'evidence.json'),JSON.stringify(evidence,null,2));
  ws?.close();for(const p of pending.values())clearTimeout(p.timer);
  const command=`$p=Get-Process -Id ${proc.pid} -ErrorAction SilentlyContinue;if($p -and $p.Path -eq '${exe.replaceAll("'","''")}'){ $null=$p.CloseMainWindow(); if(-not $p.WaitForExit(30000)){throw 'Benchmark process did not close'} }`;
  await new Promise((resolve,reject)=>execFile('powershell.exe',['-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',command],{windowsHide:true},e=>e?reject(e):resolve()));proc.unref();
 }
}
evidence.withinStartupBudget=startup.every(ms=>ms<=5000);
evidence.status=evidence.withinStartupBudget&&evidence.runs.every(r=>r.withinInteractionBudget)?'PASS':'REVIEW';await writeFile(path.join(output,'evidence.json'),JSON.stringify(evidence,null,2));

if(process.argv.includes('--strict')&&evidence.status!=='PASS')process.exitCode=2;
