import {useEffect,useRef,useState} from 'react';
import {ArrowDown,Copy,Terminal} from 'lucide-react';
import {Button} from './ui/button';
import {service} from '../services';
import type {Task} from '../types';

interface LogChunk {source:string;offset:number;text:string;reset:boolean;truncated:boolean;more:boolean;status:string;}
const states:Record<string,string>={READY:'待运行',QUEUED:'排队中',RUNNING:'处理中',SUCCESS:'已完成',FAILED:'失败',CANCELLED:'已取消'};
export function TaskLog({task,onResult}:{task?:Task;onResult:(task:Task)=>void}){
 const [text,setText]=useState(''),[error,setError]=useState(''),[following,setFollowing]=useState(true),[trimmed,setTrimmed]=useState(false);
 const view=useRef<HTMLPreElement>(null),follow=useRef(true);
 useEffect(()=>{
  let alive=true,timer:ReturnType<typeof setTimeout>,source='',offset=0;
  setText('');setError('');setTrimmed(false);follow.current=true;setFollowing(true);
  if(!task)return;
  async function poll(){
   try{
    const part=await service.call<LogChunk>('getTaskLog',{id:task!.id,source,offset});
    if(!alive)return;
    source=part.source;offset=part.offset;setError('');
    if(part.truncated)setTrimmed(true);
    if(part.reset||part.text)setText(old=>{
     const joined=(part.reset?'':old)+part.text;
     // Limit both lines and bytes: a single very long engine message is bounded too.
     const tail=joined.slice(-60000).split('\n').slice(-1000).join('\n');
     return tail;
    });
    if(part.more||['READY','QUEUED','RUNNING'].includes(part.status))timer=setTimeout(poll,part.more?150:750);
   }catch(e){if(alive){setError(String(e));timer=setTimeout(poll,2500);}}
  }
  void poll();return()=>{alive=false;clearTimeout(timer);};
 },[task?.id]);
 useEffect(()=>{if(follow.current&&view.current)view.current.scrollTop=view.current.scrollHeight;},[text]);
 const latest=()=>{follow.current=true;setFollowing(true);if(view.current)view.current.scrollTop=view.current.scrollHeight;};
 return <section className="panel task-log" aria-label="运行日志" data-task-id={task?.id}>
  <div className="panel-toolbar"><h3><Terminal size={18}/>运行日志</h3><span className="spacer"/><span className="badge">{task?states[task.status]:'等待任务'}</span>
   <Button size="sm" variant="ghost" disabled={!text} onClick={()=>void service.call('copyText',{text}).catch(e=>setError(String(e)))}><Copy size={14}/>复制日志</Button>
   <Button size="sm" variant="outline" onClick={latest}><ArrowDown size={14}/>{following?'自动滚动':'回到最新'}</Button>
  </div>
  <div className="log-context"><strong>{task?.name||'暂无运行任务'}</strong><span>{task?.status==='SUCCESS'?'清洗完成，结果已保留':task?.status==='QUEUED'?'正在排队，前一个任务结束后自动开始':task?.phase||'开始清洗后，这里显示原工具的执行日志'}</span>
   {task?.status==='SUCCESS'&&<Button size="sm" onClick={()=>onResult(task)}>查看结果</Button>}
  </div>
  {error&&<p className="error-text log-message">日志读取暂不可用：{error}</p>}
  {task?.error&&<p className="error-text log-message">{task.error.slice(-3000)}</p>}
  {task?.warning&&<p className="log-message">{task.warning}</p>}
  <pre ref={view} className="log-stream" tabIndex={0} aria-label="清洗执行日志" onScroll={()=>{const e=view.current;if(e){follow.current=e.scrollHeight-e.scrollTop-e.clientHeight<24;setFollowing(follow.current);}}}>{text||'等待原工具输出日志…'}</pre>
  <div className="log-footer">显示最近日志，最多 1,000 行；完整日志保存在本机。{trimmed?' 已略去较早内容。':''}{!following?' 已暂停自动滚动，可点击“回到最新”。':''}</div>
 </section>;
}
