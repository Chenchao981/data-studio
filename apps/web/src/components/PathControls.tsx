import {FolderOpen,Upload} from 'lucide-react';
import {Button} from './ui/button';
import type {SourceFile,Settings} from '../types';

export function PathControls({files,settings,busy,onInput,onOutput}:{files:SourceFile[];settings:Settings;busy:boolean;onInput:()=>void;onOutput:()=>void}){
 const paths=files.map(f=>f.path).join('\n');
 return <section className="panel path-controls" aria-label="输入与输出路径">
  <div className="path-controls-heading"><Upload size={18}/><h3>输入与输出</h3><span>可直接拖入文件或文件夹</span></div>
  <div className="path-control-row"><label htmlFor="input-paths">输入路径</label><div className="path-field"><textarea id="input-paths" aria-label="输入路径" readOnly value={paths} rows={Math.min(4,Math.max(2,files.length))} placeholder={settings.inputDirectory+'（选择数据源后开始）'}/><small>{files.length?`已识别 ${files.filter(f=>f.folder).length} 个文件夹、${files.filter(f=>!f.folder).length} 个文件`:'尚未选择输入'} · 文件、文件夹和压缩包统一选择</small></div><Button variant="outline" disabled={busy} onClick={onInput}><FolderOpen size={16}/>选择数据源</Button></div>
  <div className="path-control-row"><label htmlFor="output-directory">输出目录</label><div className="path-field"><textarea id="output-directory" aria-label="输出目录" readOnly rows={2} value={settings.outputDirectory}/><small>此目录自动记为默认值；清洗后另建批次和时间目录，同名不覆盖</small></div><Button variant="outline" disabled={busy} onClick={onOutput}><FolderOpen size={16}/>选择输出目录</Button></div>
  <div className="path-start">上次输入目录：<span>{settings.inputDirectory}</span></div>
 </section>;
}
