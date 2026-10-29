import type {DataService,RpcMethod} from '../types';
type Bridge={imported?:{connect:(fn:(ids:string)=>void)=>void};request:(id:string,method:string,params:string)=>void;response:{connect:(fn:(id:string,result:string)=>void)=>void};changed:{connect:(fn:()=>void)=>void};notification:{connect:(fn:(message:string)=>void)=>void}};
declare global {interface Window {qt?:{webChannelTransport:unknown};QWebChannel?:new(transport:unknown,cb:(channel:{objects:{studio:Bridge}})=>void)=>unknown;}}
export class DesktopDataService implements DataService {
  mode='desktop' as const;
  private bridge:Promise<Bridge>;
  private listeners=new Set<()=>void>();
  private pending=new Map<string,{resolve:(value:unknown)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>}>();
  constructor(){this.bridge=new Promise((resolve,reject)=>{
    if(!window.QWebChannel||!window.qt)return reject(new Error('本地通信组件未加载，请重新启动客户端。'));
    new window.QWebChannel(window.qt.webChannelTransport,channel=>{
      const b=channel.objects.studio;
      b.response.connect((id,result)=>{const p=this.pending.get(id);if(!p)return;clearTimeout(p.timer);this.pending.delete(id);try{const data=JSON.parse(result);data.ok?p.resolve(data.value):p.reject(new Error(data.error));}catch{p.reject(new Error('本地服务返回了无效响应'));}});
      b.imported?.connect(ids=>window.dispatchEvent(new CustomEvent('studio-imported',{detail:JSON.parse(ids)})));b.changed.connect(()=>this.listeners.forEach(fn=>fn()));b.notification.connect(message=>window.dispatchEvent(new CustomEvent('studio-notice',{detail:message})));resolve(b);
    });
  });}
  async call<T>(method:RpcMethod,params:Record<string,unknown>={}):Promise<T>{
    const bridge=await this.bridge;const id=crypto.randomUUID();
    return new Promise<T>((resolve,reject)=>{const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error('请求超时，请查看历史任务状态后重试。'));},60000);this.pending.set(id,{resolve:resolve as (v:unknown)=>void,reject,timer});bridge.request(id,method,JSON.stringify(params));});
  }
  subscribe(fn:()=>void){this.listeners.add(fn);return()=>{this.listeners.delete(fn);};}
}
