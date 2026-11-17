import { useQuery } from '@tanstack/react-query';
import { request } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

export type QualityDefinition={available:boolean;provisional:boolean;fields:{key:string;label:string}[];definition:string};
export type QualitySummary=QualityDefinition & {total:number;complete:number|null;incomplete:number|null;missing_counts:Record<string,number>;formatting:Record<string,{variant_groups:number;edge_whitespace_count:number}>};
export function QualitySummaryCard({quality}:{quality?:QualitySummary}){
  if(!quality)return null;
  return <section className="card workspace-card profile-quality-card" aria-label="Qualité du portefeuille autorisé"><h2>Complétude technique CRM · provisoire</h2><p>{quality.available?`${quality.complete} profil(s) à 100 % · ${quality.incomplete} incomplet(s) sur ${quality.total} clients visibles`:'Évaluation indisponible : aucun champ technique configuré.'}</p><p className="muted">{quality.definition}</p>{quality.fields.map(f=><span key={f.key} className="mr-4">{f.label} absent : {quality.missing_counts[f.key]}</span>)}<p className="muted">Variantes de libellés détectées (casse/espaces ordinaires, sans fusion) : {Object.entries(quality.formatting).map(([key,v])=>`${key==='profession'?'Profession':'Secteur'} : ${v.variant_groups} groupe(s), ${v.edge_whitespace_count} valeur(s) avec espaces en bordure`).join(' · ')}. Les doublons d’identité ne sont pas évalués.</p></section>;
}
export function ProfileQuality({id,version}:{id:string;version:number}){
  const auth=useAuth();
  const quality=useQuery({queryKey:['profile-quality',auth.identity?.session.id,id,version],queryFn:({signal})=>request<QualityDefinition & {percentage:number|null;missing_fields:{key:string;label:string}[];ownership:Record<string,string>}>(`/api/clients/${id}/quality/`,{signal}),retry:false});
  return <section className="card workspace-card profile-quality-card" aria-label="Complétude du profil"><h2>Complétude technique CRM · provisoire</h2>{quality.isError?<p role="alert">Évaluation inaccessible. Actualisez vos droits ou rechargez la fiche.</p>:!quality.data?<p>Chargement de la qualité…</p>:<><strong>{quality.data.available?`${quality.data.percentage} %`:'Non calculable'}</strong><p className="muted">{quality.data.definition}</p><p>Informations absentes : {quality.data.missing_fields.map(f=>f.label).join(', ')|| (quality.data.available?'aucune dans la définition technique':'définition indisponible')}</p><p>{quality.data.ownership.crm}</p><p>{quality.data.ownership.source}</p></>}</section>;
}
