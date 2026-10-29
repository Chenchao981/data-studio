import {FolderOpen,Upload} from 'lucide-react';
import {useEffect,useState} from 'react';
import {Button} from './ui/button';
import type {SourceFile,Settings} from '../types';

export function PathControls({files,settings,busy,onInput,onOutput,onApplyInput,onApplyOutput,onEditingChange}:{files:SourceFile[];settings:Settings;busy:boolean;onInput:()=>void;onOutput:()=>void;onApplyInput:(text:string)=>Promise<string>;onApplyOutput:(text:string)=>Promise<string>;onEditingChange:(editing:boolean)=>void}){
 const paths=files.map(f=>f.path).join('\n');
 const [input,setInput]=useState(paths);const [output,setOutput]=useState(settings.outputDirectory);
 const [inputError,setInputError]=useState('');const [outputError,setOutputError]=useState('');
 const inputDirty=input!==paths,outputDirty=output!==settings.outputDirectory;
 useEffect(()=>{setInput(paths);setInputError('');},[paths]);
 useEffect(()=>{setOutput(settings.outputDirectory);setOutputError('');},[settings.outputDirectory]);
 useEffect(()=>{onEditingChange(inputDirty||outputDirty);},[inputDirty,outputDirty,onEditingChange]);
 useEffect(()=>()=>onEditingChange(false),[onEditingChange]);
 function editInput(value:string){setInput(value);setInputError('');onEditingChange(value!==paths||outputDirty);}
 function editOutput(value:string){setOutput(value);setOutputError('');onEditingChange(inputDirty||value!==settings.outputDirectory);}
 function cancelInput(){setInput(paths);setInputError('');onEditingChange(outputDirty);}
 function cancelOutput(){setOutput(settings.outputDirectory);setOutputError('');onEditingChange(inputDirty);}
 async function applyInput(){if(busy||!inputDirty)return;try{setInput(await onApplyInput(input));setInputError('');}catch(e){setInputError(String(e).replace(/^Error: /,''));}}
 async function applyOutput(){if(busy||!outputDirty)return;try{setOutput(await onApplyOutput(output));setOutputError('');}catch(e){setOutputError(String(e).replace(/^Error: /,''));}}
 return <section className="panel path-controls" aria-label="输入与输出路径">
  <div className="path-controls-heading"><Upload size={18}/><h3>输入与输出</h3></div>
  <div className="path-control-row"><label htmlFor="input-paths">输入路径</label><div className="path-field"><textarea id="input-paths" aria-label="输入路径" aria-invalid={!!inputError} disabled={busy} value={input} onChange={e=>editInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();void applyInput();}if(e.key==='Escape')cancelInput();}} rows={Math.min(4,Math.max(2,input.split('\n').length))} placeholder="粘贴文件或文件夹路径，多项分行填写"/>{inputDirty&&<div className="path-edit-actions"><Button size="sm" disabled={busy} onClick={()=>void applyInput()}>应用输入路径</Button><Button variant="ghost" size="sm" disabled={busy} onClick={cancelInput}>取消修改</Button></div>}{inputError&&<p className="path-error" role="alert">{inputError}</p>}</div><Button variant="outline" disabled={busy} onClick={onInput}><FolderOpen size={16}/>选择数据源</Button></div>
  <div className="path-control-row"><label htmlFor="output-directory">输出目录</label><div className="path-field"><textarea id="output-directory" aria-label="输出目录" aria-invalid={!!outputError} disabled={busy} rows={2} value={output} onChange={e=>editOutput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void applyOutput();}if(e.key==='Escape')cancelOutput();}}/>{outputDirty&&<div className="path-edit-actions"><Button size="sm" disabled={busy} onClick={()=>void applyOutput()}>应用输出路径</Button><Button variant="ghost" size="sm" disabled={busy} onClick={cancelOutput}>取消修改</Button></div>}{outputError&&<p className="path-error" role="alert">{outputError}</p>}</div><Button variant="outline" disabled={busy} onClick={onOutput}><FolderOpen size={16}/>选择输出目录</Button></div>
 </section>;
}
