import {memo} from 'react';
import {BarChart3,Check,SlidersHorizontal} from 'lucide-react';
import {FactoryPicker} from './FactoryPicker';
import type {Tool,Task} from '../types';

export const factoryNames:Record<string,string>={HUAHONG:'华虹',LION:'立昂微',JETECH:'佳泰',GUOYU:'国宇 FRD',JIEQUN:'杰群',RIYUEXIN:'日月新',RIYUEGUANG:'日月光',JIEMIN:'上海捷敏',DIANJI:'电基',JIJIA:'集佳'};
// Display correction only; persisted task receipts and original files stay immutable.
export function taskParserLabel(task:Task){const factory=task.parameters?.factory||task.receipt?.factory||'';if(task.parameters?.operation==='QUICK_PAT'&&factoryNames[factory])return `${factoryNames[factory]}PAT统计`;return (factory==="JETECH"||task.toolCode?.includes("_JETECH_"))?task.parser.replaceAll("积塔","佳泰"):task.parser;}

export function operationLabel(t:Tool){if(t.tool_code==='LOCAL_CP_HUAHONG_CLEAN_V1')return '华虹数据清洗';if(t.analysis_type==='QUICK_PAT')return `${factoryNames[t.factory_code]||t.factory_code}PAT统计`;if(t.test_stage!=='FT')return t.display_name;if(t.analysis_type==='QUICK_SYL_SBL')return 'SBL / SYL';if(t.analysis_type==='QUICK_CHART')return '图表分析';return t.profile==='native'?t.display_name.replace(/ 数据清洗$/,''):'数据清洗';}

export const WorkflowChooser=memo(function WorkflowChooser({tools,stage,factory,code,onChange}:{tools:Tool[];stage:string;factory:string;code:string;onChange:(stage:string,factory:string,code:string)=>void}){
 tools=tools.filter(t=>!t.hidden && !(t.test_stage==='FT' && (t.tool_code.endsWith('_CLEANED_PAT_V1') || (t.factory_code==='JIJIA' && t.analysis_type==='QUICK_PAT'))));
 const factories=[...new Set(tools.filter(t=>t.test_stage===stage).map(t=>t.factory_code))];
 const matching=tools.filter(t=>t.test_stage===stage&&t.factory_code===factory);
 const clean=matching.filter(t=>t.analysis_type==='QUICK_CLEAN');
 const native=clean.filter(t=>t.profile==='native');
 const cleaners=[...(native.length?native:clean)].sort((a,b)=>cleaningOrder(a)-cleaningOrder(b));
 const pat=matching.filter(t=>t.analysis_type==='QUICK_PAT');
 const yieldTools=matching.filter(t=>t.analysis_type==='QUICK_SYL_SBL');
 const charts=matching.filter(t=>t.analysis_type==='QUICK_CHART');
 function cleaningOrder(t:Tool){if(stage!=='CP'||factory!=='HUAHONG')return 0;return t.tool_code==='LOCAL_CP_HUAHONG_CLEAN_V1'?0:t.tool_code==='LOCAL_CP_HUAHONG_TD_V1'?1:2;}
 function change(s:string,f:string){if(s===stage&&f===factory)return;const clean=tools.filter(t=>t.test_stage===s&&t.factory_code===f&&t.analysis_type==='QUICK_CLEAN'&&t.enabled);const native=clean.filter(t=>t.profile==='native');const options=native.length?native:clean;onChange(s,f,options.length===1?options[0].tool_code:'');}

 function cards(items:Tool[]){return items.map(t=><button key={t.tool_code} className={`operation-card ${code===t.tool_code?'selected':''}`} aria-pressed={code===t.tool_code} data-tool={t.tool_code} disabled={!t.enabled} title={t.disabled_reason||t.help} onClick={()=>onChange(stage,factory,t.tool_code)}><span>{operationLabel(t)}</span><Check className="operation-check" size={16} aria-hidden="true"/></button>);}
 function group(items:Tool[],name:string){return !!items.length&&<div className="operation-cards" role="group" aria-label={name}>{cards(items)}</div>;}
 return <section className="panel workflow-config" aria-label="分析配置">
 <FactoryPicker key={stage} factories={factories.map(f=>({code:f,name:factoryNames[f]||f,count:tools.filter(t=>t.test_stage===stage&&t.factory_code===f&&t.enabled).length}))} selected={factory} onSelect={f=>change(stage,f)}/>
 <section className="chooser-step chooser-operation" aria-labelledby="choose-operation-title"><h4 id="choose-operation-title"><span className="chooser-number"><SlidersHorizontal size={14}/></span>选择功能</h4>
 <div className="operation-groups">{group(cleaners,'清洗操作')}{group(pat,stage==='CP'?'其他分析操作':'参数分析操作')}{group(yieldTools,'良率分析操作')}{stage==='CP'&&group(charts,'图表操作')}</div>
 </section>
 {stage==='FT'&&!!charts.length&&<section className="chooser-step chooser-charts" aria-label="独立图表分析"><h4><BarChart3 size={16}/>独立图表分析</h4><div className="operation-cards" role="group" aria-label="图表操作">{cards(charts)}</div></section>}
 </section>;
});
