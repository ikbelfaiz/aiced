import { useState } from 'react';
import { useQuery,useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { request,mutate } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { Button,StatePanel } from '../../components/ui';
import { DataEditor,type Field } from '../../components/DataEditor';
import { Plus,Search } from 'lucide-react';

type Campaign={id:string;organization_id:string;name:string;description:string;targeting_notes:string;planned_start:string|null;planned_end:string|null;status:'draft';version:number;can_edit:boolean};
type Page={count:number;next:string|null;previous:string|null;results:Campaign[];business_timezone:string;business_date:string};
type Context={organizations:{id:string;name:string}[];business_timezone:string;business_date:string};
const date=(value:string|null)=>value?value.split('-').reverse().join('/'):'Non renseignée';

export function CampaignsPage(){
  const auth=useAuth();const cache=useQueryClient();const [params,setParams]=useSearchParams();
  const [draft,setDraft]=useState(params.get('search')??'');
  const [editor,setEditor]=useState<Campaign|'new'|null>(null);
  const allowed=auth.can('opportunities.view');
  const query=useQuery({queryKey:['campaigns',auth.identity?.session.id,params.toString()],queryFn:({signal})=>request<Page>(`/api/campaigns/?${params}`,{signal}),enabled:allowed,retry:false});
  const context=useQuery({queryKey:['campaign-context',auth.identity?.session.id],queryFn:({signal})=>request<Context>('/api/campaigns/context/',{signal}),enabled:allowed,retry:false});
  function filter(key:string,value:string){const next=new URLSearchParams(params);next.delete('page');if(value)next.set(key,value);else next.delete(key);setParams(next);}
  if(!allowed)return <StatePanel kind="denied" title="Campagnes non autorisées">Une habilitation commerciale est requise pour préparer vos brouillons.</StatePanel>;
  if(query.isError||context.isError)return <StatePanel kind="error" title="Campagnes inaccessibles" retry={()=>{void query.refetch();void context.refetch();}}>{query.error?.message??context.error?.message}</StatePanel>;
  if(query.isPending||context.isPending)return <StatePanel kind="loading" title="Chargement des campagnes…"/>;
  const current=editor&&editor!=='new'?editor:null;
  const fields:Field[]=[...(editor==='new'?[{name:'organization_id',label:'Organisation',required:true,options:context.data.organizations.map(o=>({value:o.id,label:o.name}))}]:[]),
    {name:'name',label:'Nom de la campagne',required:true,maxLength:160},
    {name:'description',label:'Description',type:'textarea',maxLength:5000},
    {name:'planned_start',label:'Début prévu',type:'date'},
    {name:'planned_end',label:'Fin prévue',type:'date'},
    {name:'targeting_notes',label:'Préparation du ciblage (notes non exécutées)',type:'textarea',maxLength:2000}];
  const selected=params.get('campagne');
  return <>
    <div className="page-heading"><div><p className="page-eyebrow">AICED · ACTIVITÉ</p><h1>Mes brouillons de campagnes</h1><p className="page-subtitle">Préparez vos campagnes commerciales dans votre espace personnel · {context.data.business_timezone}</p></div><Button variant="primary" disabled={!context.data.organizations.length} onClick={()=>setEditor('new')}><Plus size={16}/>Nouveau brouillon</Button></div>
    <p className="availability-note">Brouillons privés au créateur, à titre provisoire. Aucun client associé ni effectif calculé. Les notes de ciblage ne sont pas appliquées. L’activation et les communications attendent les règles AMEN INVEST.</p>
    <section className="primary-metrics campaign-metrics" aria-label="Synthèse des campagnes"><article className="card metric-card"><p>Mes brouillons</p><strong>{query.data.count}</strong><span className="muted">Dans la sélection actuelle</span></article><article className="card metric-card"><p>Clients ciblés</p><strong>—</strong><span className="muted">Ciblage non disponible</span></article><article className="card metric-card"><p>Clients intéressés</p><strong>—</strong><span className="muted">Suivi non disponible</span></article><article className="card metric-card"><p>Taux de conversion</p><strong>—</strong><span className="muted">Méthode non approuvée</span></article></section>
    <section className="card history-filters" aria-label="Filtres des campagnes"><form className="history-search" onSubmit={e=>{e.preventDefault();filter('search',draft);}}><label className="sr-only" htmlFor="campaign-search">Rechercher mes brouillons</label><div><div className="pipeline-search-input"><Search size={16}/><input id="campaign-search" placeholder="Rechercher mes brouillons…" value={draft} maxLength={200} onChange={e=>setDraft(e.target.value)}/></div><Button type="submit">Rechercher</Button></div></form>
      <div className="history-filter-fields"><label>Trier par<select aria-label="Trier par" value={params.get('ordering')??'-updated_at'} onChange={e=>filter('ordering',e.target.value)}><option value="-updated_at">Modification récente</option><option value="updated_at">Modification ancienne</option><option value="name">Nom A–Z</option><option value="-name">Nom Z–A</option><option value="planned_start">Début prévu croissant</option><option value="-planned_start">Début prévu décroissant</option></select></label><Button disabled title="Statuts et lancement à approuver par AMEN INVEST">Activation indisponible</Button><Button disabled title="Aucune communication automatique">Envoi indisponible</Button></div></section>
    <section className="campaign-results"><h2>Brouillons personnels</h2><p className="muted">{query.data.count} brouillon(s). Dates civiles dans le fuseau {context.data.business_timezone}.</p>
      {!query.data.results.length?<StatePanel kind="empty" title="Aucun brouillon dans cette sélection"/>:<div className="campaign-grid">{query.data.results.map(item=><article key={item.id} className="card campaign-draft"><div className="campaign-card-top"><span className="campaign-status">Brouillon</span>{item.can_edit&&<Button variant="text" onClick={()=>setEditor(item)} aria-label={`Modifier ${item.name}`}>Modifier →</Button>}</div><h3>{item.name}</h3><p className="history-notes campaign-description">{item.description||'Aucune description.'}</p><p className="campaign-dates">Du {date(item.planned_start)} au {date(item.planned_end)}</p><details open={selected===item.id}><summary>Consulter la préparation</summary><p className="history-notes">{item.targeting_notes||'Aucune note de ciblage.'}</p><p className="muted">Préparation uniquement ; aucune cible ni communication créée.</p></details></article>)}</div>}
      <div className="pagination"><span>{query.data.count} brouillon(s) · page {Number(params.get('page')??1)}</span><div><label>Lignes par page<select aria-label="Lignes par page" value={params.get('page_size')??'8'} onChange={e=>filter('page_size',e.target.value)}>{[8,20,50].map(n=><option key={n}>{n}</option>)}</select></label>{[-1,1].map((delta,i)=><Button key={delta} disabled={i===0?!query.data.previous:!query.data.next} onClick={()=>{const next=new URLSearchParams(params);next.set('page',String(Number(params.get('page')??1)+delta));setParams(next);}}>{i===0?'Précédent':'Suivant'}</Button>)}</div></div>
    </section>
    {editor&&<DataEditor title={current?'Modifier le brouillon':'Nouveau brouillon de campagne'} description="Préparation privée uniquement. Les dates sont facultatives ; aucune affectation, activation ou prise de contact." fields={fields} initial={{name:current?.name??'',description:current?.description??'',targeting_notes:current?.targeting_notes??'',planned_start:current?.planned_start??'',planned_end:current?.planned_end??''}} close={()=>setEditor(null)} save={async values=>{await mutate(current?`/api/campaigns/${current.id}/`:'/api/campaigns/',{...values,planned_start:values.planned_start||null,planned_end:values.planned_end||null,...(current?{version:current.version}:{})},current?'PATCH':'POST');await cache.invalidateQueries({queryKey:['campaigns']});}}/>}
  </>;
}
