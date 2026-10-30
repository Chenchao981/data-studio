import type {Task} from '../types';

// Old history may only contain timestamps. Never count queue waiting as cleaning.
export function taskSeconds(task:Task, now=Date.now()):number|undefined {
 if(task.elapsedSeconds!==undefined&&Number.isFinite(task.elapsedSeconds))return Math.max(0,task.elapsedSeconds);
 if(!task.started)return;
 const start=Date.parse(task.started),end=task.finished?Date.parse(task.finished):now;
 if(Number.isFinite(start)&&Number.isFinite(end)&&end>=start)return (end-start)/1000;
}
export function duration(seconds?:number):string {
 if(seconds===undefined)return '—';
 const rounded=Math.round(seconds*10)/10;
 if(rounded<60)return `${rounded.toFixed(1)} 秒`;
 const total=Math.round(seconds);
 return `${Math.floor(total/60)} 分 ${total%60} 秒`;
}
