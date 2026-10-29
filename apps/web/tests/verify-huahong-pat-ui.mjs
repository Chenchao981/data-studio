// Actual frozen Windows client through its temporary, loopback-only Qt CDP port.
// Seed a private workspace with a completed real task before running.
// Inputs are intentionally cleared at each application startup.
// Usage from repository root: node apps/web/tests/verify-huahong-pat-ui.mjs <exe> <private-home> <evidence-directory>
import {spawn,execFile} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';

if(process.argv.length!==5)throw Error('Usage: node apps/web/tests/verify-huahong-pat-ui.mjs <exe> <private-home-with-one-successful-HuaHong-PAT> <new-evidence-directory>');
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
 if(process.env.STUDIO_EXPECTED_VERSION&&!await evaluate(`document.querySelector('.version').textContent.includes(${JSON.stringify(process.env.STUDIO_EXPECTED_VERSION)})`))throw Error('Installed interface version differs from installer');
 await click('[data-stage=FT]');
 if(await evaluate(`document.querySelectorAll('[data-factory]').length`)<6)throw Error('FT factory catalog missing');
 await click('[data-stage=CP]');
 await evaluate(`window.calls=[];const t=qt.webChannelTransport;const old=t.send.bind(t);t.send=raw=>{try{const m=JSON.parse(raw);if(m.args)calls.push(m.args[1]);}catch{}return old(raw);};`);
 await click('[data-stage=CP]');await click('[data-factory=HUAHONG]');
 const pat='[data-tool=LOCAL_CP_HUAHONG_RAW_PAT_V1]';
 await click(pat);
 if(!await evaluate(`document.querySelector('${pat}').getAttribute('aria-pressed')==='true'`))throw Error('New PAT entry cannot be selected');
 const buttons=await evaluate(`[...document.querySelectorAll('[data-tool]')].map(e=>({code:e.dataset.tool,text:e.textContent}))`);
 if(buttons.filter(b=>b.text.includes('PAT')).length!==1)throw Error('Ambiguous PAT entries');
 if(!buttons.some(b=>b.text.includes('FT口径')))throw Error('FT formula label missing');
 if(!await evaluate(`document.querySelector('${pat}').title.includes('同一产品汇总计算并输出一个PAT Excel')`))throw Error('Product aggregation tooltip missing');
 if(await evaluate(`!!document.querySelector('.input-guide, .source-hint, .path-start, .path-field small')`))throw Error('Repeated workspace hints remain');
 await screenshot('huahong-raw-pat');
 await button('历史记录');
 const patHistory=`[...document.querySelectorAll('.history-list article')].filter(a=>a.textContent.includes('FT口径')&&[...a.querySelectorAll('button')].some(b=>b.textContent.trim()==='查看结果'))`;
 await wait(`(${patHistory}).length>0`);
 if(await evaluate(`(${patHistory}).length`)!==1)throw Error('Use a private home with exactly one successful HuaHong raw PAT task');
 await evaluate(`[...(${patHistory})[0].querySelectorAll('button')].find(b=>b.textContent.trim()==='查看结果').click()`);
 await wait(`!!document.querySelector('.result-directory') && document.body.innerText.includes('打开结果文件夹')`);
 if(await evaluate(`!!document.querySelector('.ag-root') || calls.includes('getPreview')`))throw Error('Spreadsheet preview loaded');
 await screenshot('huahong-pat-result');
 if(errors.length)throw Error(JSON.stringify(errors));
 await writeFile(path.join(output,'evidence.json'),JSON.stringify({status:'PASS',exe,buttons,checks:['Frozen application exposes FT-aligned HuaHong PAT','One Excel per product explained','New PAT selectable','Verified real result reopened from history','No Excel preview request'],uiErrors:errors},null,2));
 console.log('PASS: bundled HuaHong PAT entry and real history result');
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
