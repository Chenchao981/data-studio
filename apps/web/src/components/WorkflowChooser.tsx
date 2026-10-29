import {memo} from 'react';
import {BarChart3,Check,Info,SlidersHorizontal} from 'lucide-react';
import {FactoryPicker} from './FactoryPicker';
import type {Tool,Task} from '../types';

export const factoryNames:Record<string,string>={HUAHONG:'华虹',LION:'立昂微',JETECH:'佳泰',GUOYU:'国宇 FRD',JIEQUN:'杰群',RIYUEXIN:'日月新',RIYUEGUANG:'日月光',JIEMIN:'上海捷敏',DIANJI:'电基',JIJIA:'集佳'};
// Display correction only; persisted task receipts and original files stay immutable.
export function taskParserLabel(task:Task){return (task.parameters?.factory==="JETECH"||task.receipt?.factory==="JETECH"||task.toolCode?.includes("_JETECH_"))?task.parser.replaceAll("积塔","佳泰"):task.parser;}

export const WorkflowChooser=memo(function WorkflowChooser({tools,stage,factory,code,onChange}:{tools:Tool[];stage:string;factory:string;code:string;onChange:(stage:string,factory:string,code:string)=>void}){
 tools=tools.filter(t=>!t.hidden && !(t.test_stage==='FT' && (t.tool_code.endsWith('_CLEANED_PAT_V1') || (t.factory_code==='JIJIA' && t.analysis_type==='QUICK_PAT'))));
 const factories=[...new Set(tools.filter(t=>t.test_stage===stage).map(t=>t.factory_code))];
 const matching=tools.filter(t=>t.test_stage===stage&&t.factory_code===factory);
 const chosen=matching.find(t=>t.tool_code===code);
 const clean=matching.filter(t=>t.analysis_type==='QUICK_CLEAN');
 const native=clean.filter(t=>t.profile==='native');
 const cleaners=native.length?native:clean;
 const primary=stage==='FT'?[...cleaners,...matching.filter(t=>t.analysis_type==='QUICK_PAT'),...matching.filter(t=>t.analysis_type==='QUICK_SYL_SBL')]:cleaners;
 const charts=stage==='FT'?matching.filter(t=>t.analysis_type==='QUICK_CHART'):[];
 const extra=stage==='FT'?[]:matching.filter(t=>!primary.includes(t));
 function change(s:string,f:string){if(s===stage&&f===factory)return;const clean=tools.filter(t=>t.test_stage===s&&t.factory_code===f&&t.analysis_type==='QUICK_CLEAN'&&t.enabled);const native=clean.filter(t=>t.profile==='native');const options=native.length?native:clean;onChange(s,f,options.length===1?options[0].tool_code:'');}
 function label(t:Tool){if(stage!=='FT')return t.display_name;if(t.analysis_type==='QUICK_PAT')return 'PAT（原始数据）';if(t.analysis_type==='QUICK_SYL_SBL')return 'SBL / SYL';if(t.analysis_type==='QUICK_CHART')return '图表分析';return t.profile==='native'?t.display_name.replace(/ 数据清洗$/,''):'数据清洗';}
 function cards(items:Tool[]){return items.map(t=><button key={t.tool_code} className={`operation-card ${code===t.tool_code?'selected':''}`} aria-pressed={code===t.tool_code} data-tool={t.tool_code} disabled={!t.enabled} title={t.disabled_reason||t.help} onClick={()=>onChange(stage,factory,t.tool_code)}><span>{label(t)}</span>{code===t.tool_code?<Check size={16}/>:null}</button>);}
 return <section className="panel workflow-config" aria-label="分析配置">
 <FactoryPicker key={stage} factories={factories.map(f=>({code:f,name:factoryNames[f]||f,count:tools.filter(t=>t.test_stage===stage&&t.factory_code===f&&t.enabled).length}))} selected={factory} onSelect={f=>change(stage,f)}/>
 <section className="chooser-step chooser-operation" aria-labelledby="choose-operation-title"><h4 id="choose-operation-title"><span className="chooser-number"><SlidersHorizontal size={14}/></span>选择功能</h4>
 <div className="operation-options"><div className="operation-cards" role="group" aria-label="清洗操作">{cards(primary)}</div>
 {!!extra.length&&<><div className="more-operations">其他分析<span>{extra.length} 项</span></div><div className="operation-cards secondary" role="group" aria-label="其他分析操作">{cards(extra)}</div></>}</div>
 </section>
 {!!charts.length&&<section className="chooser-step chooser-charts" aria-label="独立图表分析"><h4><BarChart3 size={16}/>独立图表分析</h4><div className="operation-cards" role="group" aria-label="图表操作">{cards(charts)}</div></section>}
 <p className="input-guide"><Info size={15}/>{chosen?.help||'请选择清洗操作；实际格式、批次和片号仍由原工具校验。'}</p></section>;
});
