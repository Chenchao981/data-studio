import {FolderOpen,Upload} from 'lucide-react';
import {Button} from './ui/button';
import type {SourceFile,Settings} from '../types';

export function PathControls({files,settings,busy,onInput,onOutput}:{files:SourceFile[];settings:Settings;busy:boolean;onInput:()=>void;onOutput:()=>void}){
 const paths=files.map(f=>f.path).join('\n');
 return <section className="panel path-controls" aria-label="输入与输出路径">
  <div className="path-controls-heading"><Upload size={18}/><h3>输入与输出</h3></div>
  <div className="path-control-row"><label htmlFor="input-paths">输入路径</label><div className="path-field"><textarea id="input-paths" aria-label="输入路径" readOnly value={paths} rows={Math.min(4,Math.max(2,files.length))} placeholder="请选择输入文件或文件夹"/></div><Button variant="outline" disabled={busy} onClick={onInput}><FolderOpen size={16}/>选择数据源</Button></div>
  <div className="path-control-row"><label htmlFor="output-directory">输出目录</label><div className="path-field"><textarea id="output-directory" aria-label="输出目录" readOnly rows={2} value={settings.outputDirectory}/></div><Button variant="outline" disabled={busy} onClick={onOutput}><FolderOpen size={16}/>选择输出目录</Button></div>
 </section>;
}
