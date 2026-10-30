import {useEffect,useRef,useState} from 'react';
import {ArrowDown,Copy,Terminal,Square,Loader2} from 'lucide-react';
import {Button} from './ui/button';
import {service} from '../services';
import {duration,taskSeconds} from './duration';
import type {Task} from '../types';

interface LogChunk {source:string;offset:number;text:string;reset:boolean;truncated:boolean;more:boolean;status:string;}
const states:Record<string,string>={READY:'待运行',QUEUED:'排队中',RUNNING:'处理中',SUCCESS:'已完成',FAILED:'失败',CANCELLED:'已取消'};
export function TaskLog({task,onResult,onCancel}:{task?:Task;onResult:(task:Task)=>void;onCancel?:(task:Task)=>void}){
 const [text,setText]=useState(''),[error,setError]=useState(''),[following,setFollowing]=useState(true),[trimmed,setTrimmed]=useState(false);
 const [clock,setClock]=useState(Date.now());
 const running=!!task&&['READY','QUEUED','RUNNING'].includes(task.status);
 useEffect(()=>{if(!running)return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[running,task?.id]);
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
    if(part.more||['READY','QUEUED','RUNNING'].includes(part.status))timer=setTimeout(poll,part.more?80:250);
   }catch(e){if(alive){setError(String(e));timer=setTimeout(poll,2500);}}
  }
  void poll();return()=>{alive=false;clearTimeout(timer);};
 },[task?.id]);
 useEffect(()=>{if(follow.current&&view.current)view.current.scrollTop=view.current.scrollHeight;},[text]);
 const latest=()=>{follow.current=true;setFollowing(true);if(view.current)view.current.scrollTop=view.current.scrollHeight;};
 return <section className="panel task-log" aria-label="运行日志" data-task-id={task?.id}>
  <div className="panel-toolbar"><h3>{running?<Loader2 size={16} className="spin"/>:<Terminal size={16}/>}实时日志</h3><span className="spacer"/><span className={`log-state ${running?'is-running':''}`}>{task?states[task.status]:'就绪'}</span>{task&&<span className="log-elapsed">{duration(taskSeconds(task,clock))}</span>}
   <Button size="sm" variant="ghost" title="复制日志" aria-label="复制日志" disabled={!text} onClick={()=>void service.call('copyText',{text}).catch(e=>setError(String(e)))}><Copy size={14}/></Button>
   <Button size="sm" variant="outline" onClick={latest}><ArrowDown size={14}/>{following?'自动滚动':'回到最新'}</Button>
  </div>
  <div className="log-context"><strong>{task?.name||'等待开始清洗'}</strong><span>{task?.status==='SUCCESS'?'清洗完成，结果已保留':task?.status==='QUEUED'?'正在排队，前一个任务结束后自动开始':task?.phase||''}</span>
   {task&&running&&onCancel&&<Button size="sm" variant="outline" onClick={()=>onCancel(task)}><Square size={12}/>取消</Button>}
   {task?.status==='SUCCESS'&&<Button size="sm" onClick={()=>onResult(task)}>查看结果</Button>}
  </div>
  {error&&<p className="error-text log-message">日志读取暂不可用：{error}</p>}
  {task?.error&&<p className="error-text log-message">{task.error.slice(-3000)}</p>}
  {task?.warning&&<p className="log-message">{task.warning}</p>}
  <pre ref={view} className="log-stream" tabIndex={0} aria-label="清洗执行日志" onScroll={()=>{const e=view.current;if(e){follow.current=e.scrollHeight-e.scrollTop-e.clientHeight<24;setFollowing(follow.current);}}}>{text||(running?'正在准备计算引擎…':'选择输入后点击“清洗”，处理状态将在这里实时显示。')}</pre>
  <div className="log-footer">完整日志已自动保留{trimmed?' 已略去较早内容。':''}{!following?' 已暂停自动滚动，可点击“回到最新”。':''}</div>
 </section>;
}
