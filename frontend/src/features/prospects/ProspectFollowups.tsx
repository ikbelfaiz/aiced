import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { request } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, StatePanel } from '../../components/ui';

const schema=z.object({count:z.number(),next:z.string().nullable(),previous:z.string().nullable(),
  business_date:z.string(),business_timezone:z.string(),buckets:z.record(z.string(),z.number()),
  results:z.array(z.object({id:z.string(),display_name:z.string(),status:z.string(),next_action:z.string(),next_action_date:z.string().nullable()}))});
const buckets:Record<string,string>={overdue:'En retard',today:'Aujourd’hui',upcoming:'À venir',unscheduled:'Sans date'};
const statuses:Record<string,string>={contact:'À contacter',qualified:'Qualifié',discussion:'En discussion',follow_up:'À relancer',closed:'Clos'};
const calendarDate=(value:string)=>value.split('-').reverse().join('/');

export function ProspectFollowups(){
  const auth=useAuth();
  const [params,setParams]=useSearchParams();
  const [draft,setDraft]=useState(params.get('search')??'');
  const allowed=auth.can('clients.view')&&auth.can('prospects.view');
  const page=Math.max(1,Number(params.get('page'))||1);
  const query=useQuery({queryKey:['prospect-followups',auth.identity?.session.id,params.toString()],
    queryFn:async({signal})=>schema.parse(await request(`/api/prospects/follow-ups/?${params}`,{signal})),
    enabled:allowed,retry:false,refetchInterval:60000,refetchOnWindowFocus:'always'});
  function filter(key:string,value:string){const next=new URLSearchParams(params);next.delete('page');if(value)next.set(key,value);else next.delete(key);setParams(next);}
  function go(value:number){const next=new URLSearchParams(params);next.set('page',String(value));setParams(next);}
  if(!allowed)return <StatePanel kind="denied" title="Relances non autorisées">Les habilitations clients et prospects sont requises.</StatePanel>;
  return <>
    <div className="page-heading"><div><h1>Relances prospects</h1><p className="page-subtitle">Prochaines actions saisies dans les fiches de votre périmètre.</p></div><Link className="button button-primary" to="/prospects">Qualifier les prospects</Link></div>
    <section className="client-filters history-filters" aria-label="Filtres des relances">
      <form className="history-search" onSubmit={e=>{e.preventDefault();filter('search',draft);}}><label htmlFor="followup-search">Rechercher un prospect ou une action</label><div><input id="followup-search" value={draft} maxLength={200} onChange={e=>setDraft(e.target.value)}/><Button type="submit">Rechercher</Button></div></form>
      <div className="history-filter-fields">
        <label>Échéance<select aria-label="Échéance" value={params.get('bucket')??''} onChange={e=>filter('bucket',e.target.value)}><option value="">Toutes les échéances</option>{Object.entries(buckets).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Statut<select aria-label="Statut" value={params.get('status')??''} onChange={e=>filter('status',e.target.value)}><option value="">Tous les statuts</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Depuis le<input type="date" value={params.get('date_from')??''} onChange={e=>filter('date_from',e.target.value)}/></label>
        <label>Jusqu’au<input type="date" value={params.get('date_to')??''} onChange={e=>filter('date_to',e.target.value)}/></label>
        <label>Trier par<select aria-label="Trier par" value={params.get('ordering')??'next_action_date'} onChange={e=>filter('ordering',e.target.value)}><option value="next_action_date">Date croissante</option><option value="-next_action_date">Date décroissante</option><option value="display_name">Nom A–Z</option><option value="-display_name">Nom Z–A</option></select></label>
        <Button variant="text" onClick={()=>{setDraft('');setParams({});}}>Réinitialiser les filtres</Button>
      </div>
      <p className="muted">Dates calendaires selon Africa/Tunis. Tous les statuts sont inclus, y compris Clos. Sans date inclut les prospects sans action saisie ; une borne de date les exclut.</p>
    </section>
    {query.isPending?<StatePanel kind="loading" title="Chargement des relances…"/>:query.isError?<StatePanel kind="error" title="Impossible de charger les relances" retry={()=>void query.refetch()}>{query.error.message}</StatePanel>:<>
      <p aria-live="polite">Date métier : {calendarDate(query.data.business_date)} · {query.data.business_timezone}</p>
      <p aria-label="Compteurs des échéances">{Object.entries(buckets).map(([key,label])=><span key={key}>{label} : {query.data.buckets[key]} · </span>)}</p>
      <p className="muted">Compteurs après recherche, statut et dates, avant le filtre d’échéance. Actualisation chaque minute.</p>
      {!query.data.results.length?<StatePanel kind="empty" title="Aucun prospect dans cette sélection">Modifiez les filtres ou qualifiez une prochaine action depuis la liste des prospects.</StatePanel>:
        <div className="client-table-card"><div className="table-scroll" tabIndex={0} aria-label="Tableau des relances"><table className="history-table"><thead><tr>{['Prospect','Statut','Prochaine action','Date','Fiche'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{query.data.results.map(row=><tr key={row.id}><th scope="row">{row.display_name}</th><td>{statuses[row.status]}</td><td>{row.next_action||'Aucune action saisie'}</td><td>{row.next_action_date?<time dateTime={row.next_action_date}>{calendarDate(row.next_action_date)}</time>:'Sans date'}</td><td><Link className="text-link" to={`/clients/${row.id}`}>Ouvrir la fiche de {row.display_name}</Link></td></tr>)}</tbody></table></div>
        <div className="pagination"><span>{query.data.count} prospect(s) · page {page}</span><div><label>Lignes par page <select aria-label="Lignes par page" value={params.get('page_size')??'8'} onChange={e=>filter('page_size',e.target.value)}>{[8,20,50].map(n=><option key={n}>{n}</option>)}</select></label><Button disabled={!query.data.previous} onClick={()=>go(page-1)}>Précédent</Button><Button disabled={!query.data.next} onClick={()=>go(page+1)}>Suivant</Button></div></div></div>}
    </>}
  </>;
}
