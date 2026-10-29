// Actual frozen client: user text input -> trusted bridge -> real CP/FT jobs.
import {spawn,execFile} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
if(process.argv.length!==7)throw Error('Usage: node apps/web/tests/verify-editable-paths.mjs <exe> <new-home> <new-evidence> <CP ZIP> <Jiemin DC file>');
const [exe,home,out,cp,ft]=process.argv.slice(2).map(v=>path.resolve(v));
await mkdir(home,{recursive:false});await mkdir(out,{recursive:true});
const output=path.join(out,'输出 中文');await mkdir(output);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>!/^(PYTHON|CONDA|QT)/.test(k)));
env.PATH=process.env.SystemRoot+'\\System32;'+process.env.SystemRoot;env.QTWEBENGINE_REMOTE_DEBUGGING='127.0.0.1:'+port;
const proc=spawn(exe,['--home',home],{env,windowsHide:false,stdio:'ignore'});
let ws,serial=0;const pending=new Map(),errors=[];
function send(method,params={}){const id=++serial;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function js(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function wait(expression,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){if(await js(expression))return;await pause(80);}throw Error('Timeout: '+expression);}
async function click(text){const q=`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`;await wait(`!!(${q})`);await js(`(${q}).click()`);}
async function fill(selector,text){await wait(`!!document.querySelector(${JSON.stringify(selector)})&&!document.querySelector(${JSON.stringify(selector)}).disabled`);await js(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.focus();e.select()})()`);await send('Input.insertText',{text});await wait(`document.querySelector(${JSON.stringify(selector)}).value===${JSON.stringify(text)}`);}
async function screenshot(name){const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(path.join(out,name+'.png'),Buffer.from(r.data,'base64'));}
try{
 let target;const end=Date.now()+60000;while(Date.now()<end){try{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p=>p.url.startsWith('studio:'));if(target)break;}catch{}await pause(100);}if(!target)throw Error('No private Studio page');
 ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.method==='Runtime.exceptionThrown')errors.push(r.params);const p=pending.get(r.id);if(!p)return;pending.delete(r.id);clearTimeout(p.timer);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result);};
 await send('Runtime.enable');await send('Page.enable');await wait(`!!document.querySelector('#input-paths')`);
 if(!await js(`!document.querySelector('#input-paths').readOnly&&!document.querySelector('#output-directory').readOnly`))throw Error('Path fields are not editable');
 await fill('#input-paths','"'+cp+'"');await fill('#output-directory',output);await screenshot('editing');
 await click('应用输出路径');await wait(`![...document.querySelectorAll('button')].some(b=>b.textContent==='应用输出路径')`);
 await click('应用输入路径');await wait(`document.querySelector('#input-paths').value===${JSON.stringify(cp)}`);
 await fill('#input-paths',path.join(out,'missing.zip'));await click('应用输入路径');await wait(`document.querySelector('#input-paths').getAttribute('aria-invalid')==='true'`);
 if(!await js(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('开始清洗')).disabled`))throw Error('Unapplied input can start an old task');
 await screenshot('invalid-input');await click('取消修改');
 const completed=[];
 for(const [stage,factory,code,source] of [['CP','HUAHONG','LOCAL_CP_HUAHONG_CLEAN_V1',cp],['FT','JIEMIN','LOCAL_FT_JIEMIN_FT_ALL_V1',ft]]){
  await js(`document.querySelector('[data-stage=${stage}]').click()`);await wait(`!!document.querySelector('[data-factory=${factory}]')`);await js(`document.querySelector('[data-factory=${factory}]').click()`);await wait(`!!document.querySelector('[data-tool=${code}]')`);await js(`document.querySelector('[data-tool=${code}]').click()`);
  if(await js(`document.querySelector('#input-paths').value`)!==source){await fill('#input-paths','"'+source+'"');await click('应用输入路径');await wait(`document.querySelector('#input-paths').value===${JSON.stringify(source)}`);}
  await click('开始清洗');
  await wait(`['已完成','失败','已取消'].includes(document.querySelector('.task-log .badge')?.textContent)`,300000);
  if(await js(`document.querySelector('.task-log .badge').textContent`)!=='已完成')throw Error(await js(`document.body.innerText`));
  await click('历史记录');await click('查看结果');await wait(`!!document.querySelector('.result-directory')`);
  if(!await js(`document.querySelector('.result-directory').textContent.includes(${JSON.stringify(output)})`))throw Error('Edited output directory was not used');
  await screenshot(stage+'-result');completed.push({stage,source});
 }
 if(errors.length)throw Error(JSON.stringify(errors));
 await writeFile(path.join(out,'evidence.json'),JSON.stringify({status:'PASS',exe,home,output,completed,uiErrors:errors,checks:['Editable text areas','Native text insertion','Dirty paths blocked','Invalid input preserves applied source','Actual CP and FT outputs use edited directory']},null,2));
 console.log('PASS: frozen editable paths and real CP/FT tasks');
}catch(error){await writeFile(path.join(out,'failure.txt'),String(error));if(ws){await writeFile(path.join(out,'failure-dom.txt'),await js('document.body.innerText'));await screenshot('failure');}throw error;
}finally{
 ws?.close();for(const p of pending.values())clearTimeout(p.timer);
 const command=`$p=Get-Process -Id ${proc.pid} -ErrorAction SilentlyContinue;if($p -and $p.Path -eq '${exe.replaceAll("'","''")}'){$null=$p.CloseMainWindow();$null=$p.WaitForExit(30000)}`;
 await new Promise(r=>execFile('powershell.exe',['-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',command],{windowsHide:true},r));proc.unref();
}
