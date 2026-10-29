export type Page = 'workspace'|'preview'|'analysis'|'history'|'platform'|'settings';
export type Status = 'READY'|'QUEUED'|'RUNNING'|'SUCCESS'|'FAILED'|'CANCELLED';
export interface SourceFile {id:string; name:string; path:string; size:number; kind:'CP'|'FT'|'UNKNOWN'; demo:boolean; folder:boolean; modified?:number;}
export interface ResultTable {id:string;name:string;rows:number;columns:number;mode:string;headers?:string[];}
export interface Tool {allowed_suffixes:string[];tool_code:string;display_name:string;factory_code:string;test_stage:string;analysis_type:string;enabled:boolean;disabled_reason?:string;help:string;profile:string;hidden?:boolean;}
export interface Task {publishedDirectory?:string;outputParent?:string;parameters?:{stage?:string;factory?:string;operation?:string};id:string; name:string; status:Status; progress:number; created:string; finished?:string; error:string; sourceId:string; sourceIds?:string[];output:string; parser:string; demo:boolean;phase?:string;toolCode?:string;followupCode?:string;parentTask?:{id:string};warning?:string;tables?:ResultTable[];artifacts?:{name:string}[];receipt?:{files:number;records:number;package:string;factory:string;stage:string};}
export interface Settings {inputDirectory:string;inputIds:string[];outputDirectory:string;theme:'light'|'dark'; output:string; concurrency:number; version:string;}
export interface Snapshot {files:SourceFile[]; tasks:Task[]; settings:Settings; root:string; demoRows:number;engines?:{ready:boolean;tools:Tool[];error:string;version:string};}
export interface PreviewRequest {dataset:'demo_raw'|'demo_clean'; start:number; end:number; search:string; sort:{colId:string;sort:'asc'|'desc'}[]; filters:Record<string,unknown>;}
export interface PreviewResponse {rows:Record<string,string|number>[]; total:number; elapsedMs:number;}
export interface ChartData {histogram:{label:string;count:number}[]; points:number[][]; count:number; mean:number; min:number; max:number; unit:string; sampleCount:number;}
export type RpcMethod='bootstrap'|'removeInputs'|'selectInputs'|'selectOutputDirectory'|'selectFiles'|'selectFolder'|'identifyFiles'|'createTask'|'startTask'|'cancelTask'|'getTaskLog'|'getTaskStatus'|'getPreview'|'getChartData'|'listHistory'|'openOutputFolder'|'exportResult'|'exportChart'|'saveSettings'|'clearCache'|'copyText'|'openLogs'|'openArtifact'|'createFollowup'|'openCPCharts'|'exportResultFolder'|'getResultDetails';
export interface DataService {
  mode:'desktop'|'mock';
  call<T>(method:RpcMethod,params?:Record<string,unknown>):Promise<T>;
  subscribe(listener:()=>void):()=>void;
}
