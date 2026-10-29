import {useMemo,useState} from 'react';
import type {Dispatch,SetStateAction} from 'react';
import type {SourceFile} from '../types';

type Draft={factory:string;toolCode:string;files:SourceFile[];selected:string[];group:boolean};
const empty=(factory:string):Draft=>({factory,toolCode:'',files:[],selected:[],group:true});

// Session-only drafts: CP and FT inputs never carry across workbenches, and a
// fresh client starts empty. Registered source IDs remain valid in local Core.
export function useWorkspaces(){
 const [stage,setStage]=useState<'CP'|'FT'>('CP');
 const [drafts,setDrafts]=useState({CP:empty('HUAHONG'),FT:empty('JIEQUN')});
 const setters=useMemo(()=>{
  function field<K extends keyof Draft>(key:K):Dispatch<SetStateAction<Draft[K]>>{
   return value=>setDrafts(old=>({...old,[stage]:{...old[stage],[key]:typeof value==='function'?(value as (previous:Draft[K])=>Draft[K])(old[stage][key]):value}}));
  }
  return {setFactory:field('factory'),setToolCode:field('toolCode'),setFiles:field('files'),setSelected:field('selected'),setGroup:field('group')};
 },[stage]);
 return {stage,setStage,...drafts[stage],...setters};
}
