import {duration,taskSeconds} from './duration';
import {taskParserLabel} from './WorkflowChooser';
import {useEffect,useState} from 'react';
import {Download,FolderOpen,FileSpreadsheet,Info,ChartNoAxesCombined,Loader2} from 'lucide-react';
import {service} from '../services';
import {Picker} from './Picker';
import {Button} from './ui/button';
import type {Task} from '../types';
export function Results({tasks,selected,onSelect,notify}:{tasks:Task[];selected:string;onSelect:(id:string)=>void;notify:(s:string)=>void}){
 const choices=tasks.filter(t=>t.status==='SUCCESS'&&!t.demo);
 const task=choices.find(t=>t.id===selected)||choices[0];
 const [details,setDetails]=useState<{id:string;directory:string;files:string[]}>();const [working,setWorking]=useState(false);
 const info=details?.id===task?.id?details:undefined;
 useEffect(()=>{let alive=true;if(task)void service.call<Omit<NonNullable<typeof details>,'id'>>('getResultDetails',{id:task.id}).then(r=>{if(alive)setDetails({...r,id:task.id});}).catch(e=>{if(alive)notify(String(e));});return()=>{alive=false;};},[task?.id,notify]);
 async function action(method:'exportResult'|'openOutputFolder'|'openCPCharts'|'exportResultFolder'){if(!task)return;setWorking(true);try{const result=await service.call(method,{id:task.id});if(method==='exportResultFolder'&&result)notify('清洗文件夹已保存：'+String(result));}catch(e){notify(String(e));}finally{setWorking(false);}}
 return <><div className="page-heading"><div><div className="eyebrow">YOUR VERIFIED RESULTS</div><h1>清洗结果</h1><p>结果文件已保存在本机，打开文件夹即可查看 Excel、CSV 和报告。</p></div><span className="badge">本地保存</span></div>
 {!task?<div className="panel empty"><FileSpreadsheet size={34}/><h3>还没有成功的真实分析</h3><p>在工作台选择工厂与操作，完成后在这里打开结果文件夹。</p></div>:<>
 <div className="panel result-controls"><label>分析任务<Picker label="选择分析任务" value={task.id} onChange={onSelect} options={choices.map(t=>({value:t.id,label:t.name+' · '+taskParserLabel(t)}))}/></label><div className="button-row"><Button disabled={working} onClick={()=>action('openOutputFolder')}><FolderOpen size={15}/>打开结果文件夹</Button>{task.parameters?.stage==='CP'&&task.parameters?.operation==='QUICK_CLEAN'&&<Button variant="outline" disabled={working} onClick={()=>action('openCPCharts')}>{working?<Loader2 className="spin" size={15}/>:<ChartNoAxesCombined size={15}/>}查看CP图表</Button>}{!!info?.files.length&&<Button variant="outline" disabled={working} onClick={()=>action('exportResultFolder')}>另存清洗文件夹</Button>}<Button variant="ghost" disabled={working} onClick={()=>action('exportResult')}><Download size={15}/>完整归档ZIP</Button></div></div>
 {info&&<div className="note result-directory"><FolderOpen size={15}/><span>清洗文件保存在：{info.directory}</span></div>}
 <div className="metrics compact"><div className="metric"><span>输入文件</span><strong>{task.receipt?.files??'—'}</strong></div><div className="metric"><span>输出文件</span><strong>{info?info.files.length||task.artifacts?.length||0:'—'}</strong></div><div className="metric"><span>清洗耗时</span><strong className="text-value">{duration(taskSeconds(task))}</strong></div></div>
 {task.warning&&<div className="note amber">{task.warning}</div>}
 <div className="note"><Info size={15}/>Excel、CSV 和报告直接在结果文件夹中查看。CP图表仍使用原工具的本地交互界面；完整归档ZIP用于备份结果。</div></>}
 </>;
}
