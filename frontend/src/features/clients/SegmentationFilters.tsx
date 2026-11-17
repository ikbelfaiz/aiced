import type { QualitySummary } from './ProfileQuality';
export type FilterOptions={quality:QualitySummary;kind:{kind:string;count:number}[];truncated:Record<string,boolean>;profession:{values:{value:string;count:number}[];missing_count:number};sector:{values:{value:string;count:number}[];missing_count:number}};

export function SegmentationFilters({params,options,change,disabled}:{params:URLSearchParams;options?:FilterOptions;change:(field:string,value:string)=>void;disabled:boolean}){
  return <>{(['profession','sector'] as const).map(field=>{
    const label=field==='profession'?'Profession':'Secteur';
    const raw=params.get(field);
    const value=params.get(field+'_missing')==='true'?'missing':params.get(field+'_missing')==='false'?'present':raw===null?'':JSON.stringify(raw);
    const values=options?.[field].values??[];
    return <label className="select-wrap" key={field}><span className="sr-only">{label}</span><select aria-label={label} value={value} disabled={disabled} onChange={e=>change(field,e.target.value)}>
      <option value="">{label} — toutes les valeurs</option>
      <option value="missing">Non renseigné{options?` (${options[field].missing_count})`:''}</option>
      <option value="present">Renseigné</option>
      {raw!==null&&!values.some(item=>item.value===raw)&&<option value={JSON.stringify(raw)}>Valeur sélectionnée absente du périmètre</option>}
      {values.map(item=><option key={item.value} value={JSON.stringify(item.value)}>{JSON.stringify(item.value)} ({item.count})</option>)}
    </select></label>;
  })}</>;
}
