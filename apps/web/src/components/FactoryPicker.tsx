import {useState} from 'react';
import type {CSSProperties} from 'react';
import {Building2,Check,Search,X} from 'lucide-react';

interface Factory {code:string;name:string;count:number;}
const marks:Record<string,string>={HUAHONG:'华虹',JETECH:'佳泰',LION:'立昂',GUOYU:'国宇',JIEQUN:'杰群',RIYUEXIN:'日新',JIEMIN:'捷敏',DIANJI:'电基',JIJIA:'集佳',RIYUEGUANG:'日光'};
const initials:Record<string,string>={HUAHONG:'hh',JETECH:'jt jiatai',LION:'law liangwei',GUOYU:'gy frd',JIEQUN:'jq',RIYUEXIN:'ryx',JIEMIN:'jm shjm shanghaijiemin',DIANJI:'dj',JIJIA:'jj',RIYUEGUANG:'ryg'};
const colors=['#3568bd','#168574','#8060b0','#bd7942','#528366','#557d9b'];
function accent(code:string){let hash=0;for(const c of code)hash=(hash*31+c.charCodeAt(0))>>>0;return colors[hash%colors.length];}

export function FactoryPicker({factories,selected,onSelect}:{factories:Factory[];selected:string;onSelect:(code:string)=>void}){
 const [query,setQuery]=useState('');
 const search=query.trim().toLowerCase();
 const matches=factories.filter(f=>`${f.name} ${f.code} ${initials[f.code]||''}`.toLowerCase().includes(search));
 const current=factories.find(f=>f.code===selected);
 return <section className="factory-browser" aria-labelledby="factory-title">
  <header className="factory-toolbar">
   <div className="factory-title"><span className="factory-title-icon"><Building2 size={19}/></span><div><h3 id="factory-title">选择工厂 <span>{factories.length} 家</span></h3><p>先选工厂，再选择对应功能</p></div></div>
   <div className="factory-current"><span>当前</span><strong>{current?.name||'未选择'}</strong></div>
   <div className="factory-search"><Search size={16}/><input aria-label="搜索工厂" placeholder="搜索工厂名称 / 拼音" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setQuery('');}}/>{query&&<button aria-label="清空工厂搜索" onClick={()=>setQuery('')}><X size={14}/></button>}</div>
  </header>
  <div className="factory-grid" role="group" aria-label="工厂">
   {matches.map(f=><button key={f.code} className="factory-tile" data-factory={f.code} aria-label={`选择${f.name}`} aria-pressed={selected===f.code} title={f.name} style={{'--factory-accent':accent(f.code)} as CSSProperties} onClick={()=>onSelect(f.code)}>
    <span className="factory-monogram" aria-hidden="true">{marks[f.code]||f.name.slice(0,2)}</span>
    <span className="factory-copy"><strong>{f.name}</strong><small>{f.count} 项可用功能</small></span>
    <span className="factory-selection" aria-hidden="true">{selected===f.code&&<Check size={12} strokeWidth={3}/>}</span>
   </button>)}
   {!matches.length&&<div className="factory-no-match"><Search size={20}/><strong>没有匹配的工厂</strong><span>试试中文名称或拼音；当前选择保持不变。</span><button onClick={()=>setQuery('')}>显示全部工厂</button></div>}
  </div>
  {(factories.length>8||query)&&<div className="factory-browse-hint" role="status">{query?`找到 ${matches.length} / ${factories.length} 家工厂`:'滚动查看全部工厂，或输入名称快速定位'}</div>}
 </section>;
}
