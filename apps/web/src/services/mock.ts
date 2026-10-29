import type {DataService,Snapshot,PreviewRequest,Task,RpcMethod} from '../types';
// Browser-only UI prototype. Desktop never falls back to this implementation.
export class MockDataService implements DataService {
  mode='mock' as const;
  private listeners=new Set<()=>void>();
  private state:Snapshot={root:'浏览器UI演示',demoRows:100000,settings:{inputDirectory:'桌面',inputIds:[],outputDirectory:'桌面',theme:'light',output:'桌面端管理的本地目录',concurrency:1,version:'0.1.0-m0'},tasks:[],files:[{id:'demo-cp',name:'CP_Demo_Wafer_01.csv',path:'内置演示 / CP',size:8400000,kind:'CP',demo:true,folder:false},{id:'demo-ft',name:'FT_Demo_Lot_02.csv',path:'内置演示 / FT',size:3200000,kind:'FT',demo:true,folder:false},{id:'demo-fail',name:'CP_Demo_Error.csv',path:'内置演示 / 失败恢复',size:1024,kind:'CP',demo:true,folder:false}]};
  subscribe(fn:()=>void){this.listeners.add(fn);return()=>{this.listeners.delete(fn);};}
  async call<T>(method:RpcMethod,p:Record<string,unknown>={}):Promise<T>{
    let value:unknown;
    if(method==='bootstrap')value=structuredClone(this.state);
    else if(method==='listHistory')value=this.state.tasks.filter(t=>t.name.toLowerCase().includes(String(p.search||'').toLowerCase()));
    else if(method==='getPreview') {const q=p as unknown as PreviewRequest;value={rows:Array.from({length:Math.min(200,q.end-q.start)},(_,j)=>{const i=q.start+j;return{id:i+1,product:'DEMO-IGBT',lot:`DEMO-${1+i%4}`,wafer:String(1+i%25).padStart(2,'0'),x:i%160,y:Math.floor(i/160),bv:600+Math.sin(i)*28,leakage:0.3+(i%100)/1000,bin:i%30===0?2:1};}),total:100000,elapsedMs:2};}
    else if(method==='getChartData')value={histogram:Array.from({length:24},(_,i)=>({label:String(560+i*4),count:Math.round(5000*Math.exp(-Math.pow((i-12)/5,2)))})),points:Array.from({length:1200},(_,i)=>[i,600+Math.sin(i)*25]),count:100000,mean:600,min:560,max:650,unit:'V',sampleCount:1200};
    else if(method==='createTask'){const source=this.state.files.find(f=>f.id===p.sourceId);if(!source)throw Error('请选择文件');const task:Task={id:crypto.randomUUID(),name:source.name,status:'READY',progress:0,created:new Date().toISOString(),error:'',sourceId:source.id,output:'',parser:'demo.v1',demo:true};this.state.tasks.unshift(task);value=task;}
    else if(method==='startTask'){const task=this.state.tasks.find(t=>t.id===p.id)!;task.status='RUNNING';let step=0;const timer=setInterval(()=>{if(task.status==='CANCELLED'){clearInterval(timer);return;}task.progress=++step*10;if(step===10){task.status=task.sourceId==='demo-fail'?'FAILED':'SUCCESS';task.error=task.status==='FAILED'?'模拟格式错误，用于验证失败与重试反馈。':'';clearInterval(timer);}this.listeners.forEach(fn=>fn());},250);value=true;}
    else if(method==='cancelTask'){const task=this.state.tasks.find(t=>t.id===p.id)!;task.status='CANCELLED';value=true;}
    else if(method==='saveSettings'){Object.assign(this.state.settings,p);value=this.state.settings;}
    else if(method==='identifyFiles')value=this.state.files;
    else throw Error('此操作需要在桌面客户端中使用。浏览器当前为 UI 演示模式。');
    return value as T;
  }
}
