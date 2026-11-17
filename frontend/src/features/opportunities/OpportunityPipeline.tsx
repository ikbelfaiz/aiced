import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link,useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { request } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { Button,StatePanel } from '../../components/ui';

const schema=z.object({count:z.number(),next:z.string().nullable(),previous:z.string().nullable(),statuses:z.record(z.string(),z.number()),results:z.array(z.object({
  id:z.string(),party_id:z.string(),party_name:z.string(),title:z.string(),notes:z.string(),amount:z.string().nullable(),currency:z.string(),status:z.string(),due_date:z.string().nullable(),version:z.number(),updated_at:z.string(),can_edit:z.boolean()}))});
const statuses:Record<string,string>={open:'Ouvertes',won:'Gagnées',lost:'Perdues'};

export function OpportunityPipeline(){
  const auth=useAuth();const [params,setParams]=useSearchParams();
  const [draft,setDraft]=useState(params.get('search')??'');
  const allowed=auth.can('clients.view')&&auth.can('opportunities.view');
  const query=useQuery({queryKey:['opportunity-pipeline',auth.identity?.session.id,params.toString()],queryFn:async({signal})=>schema.parse(await request(`/api/opportunities/?${params}`,{signal})),enabled:allowed,retry:false});
  const page=Math.max(1,Number(params.get('page'))||1);
  function filter(key:string,value:string){const next=new URLSearchParams(params);next.delete('page');if(value)next.set(key,value);else next.delete(key);setParams(next);}
  function go(value:number){const next=new URLSearchParams(params);next.set('page',String(value));setParams(next);}
  if(!allowed)return <StatePanel kind="denied" title="Pipeline non autorisé">Les habilitations clients et opportunités sont requises.</StatePanel>;
  return <>
    <div className="page-heading"><div><h1>Pipeline des opportunités</h1><p className="page-subtitle">Suivez les dossiers commerciaux de votre périmètre.</p></div><Link to="/clients" className="button button-primary">Créer depuis une fiche</Link></div>
    <section className="client-filters history-filters" aria-label="Filtres du pipeline"><form className="history-search" onSubmit={e=>{e.preventDefault();filter('search',draft);}}><label htmlFor="pipeline-search">Rechercher par dossier, titre ou notes</label><div><input id="pipeline-search" value={draft} maxLength={200} onChange={e=>setDraft(e.target.value)}/><Button type="submit">Rechercher</Button></div></form>
      <div className="history-filter-fields"><label>Statut<select aria-label="Statut" value={params.get('status')??''} onChange={e=>filter('status',e.target.value)}><option value="">Tous les statuts</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <label>Trier par<select aria-label="Trier par" value={params.get('ordering')??'-updated_at'} onChange={e=>filter('ordering',e.target.value)}><option value="-updated_at">Modification récente</option><option value="updated_at">Modification ancienne</option><option value="title">Titre A–Z</option><option value="-title">Titre Z–A</option><option value="due_date">Échéance croissante</option><option value="-due_date">Échéance décroissante</option></select></label>
      <Button variant="text" onClick={()=>{setDraft('');setParams({});}}>Réinitialiser les filtres</Button></div>
      <p className="muted">Les cartes représentent la page courante. Les compteurs portent sur tous les dossiers autorisés après recherche, avant le filtre de statut. Les montants sont des estimations commerciales déclarées.</p></section>
    {query.isPending?<StatePanel kind="loading" title="Chargement du pipeline…"/>:query.isError?<StatePanel kind="error" title="Impossible de charger le pipeline" retry={()=>void query.refetch()}>{query.error.message}</StatePanel>:<>
      <div className="opportunity-board">{Object.entries(statuses).filter(([key])=>!params.get('status')||params.get('status')===key).map(([status,label])=><section className="card pipeline-column" aria-label={label} key={status}><h2>{label} ({query.data.statuses[status]})</h2>
        {query.data.results.filter(row=>row.status===status).map(row=><article className="pipeline-card" key={row.id}><h3>{row.title}</h3><p>{row.party_name}</p><p>{row.amount===null?'Estimation non renseignée':`${row.amount} ${row.currency} · estimation commerciale AICED`}</p><p>Échéance : {row.due_date?row.due_date.split('-').reverse().join('/'):'Non renseignée'}</p>{row.notes&&<details><summary>Lire les notes</summary><p className="history-notes">{row.notes}</p></details>}<Link className="text-link" to={`/clients/${row.party_id}?onglet=opportunities&opportunite=${row.id}`}>{row.can_edit?'Ouvrir / modifier':'Ouvrir'} : {row.title}</Link></article>)}
        {!query.data.results.some(row=>row.status===status)&&<p className="muted">Aucune carte sur cette page.</p>}</section>)}</div>
      {!query.data.count&&<StatePanel kind="empty" title="Aucune opportunité dans cette sélection">Modifiez les filtres ou créez une opportunité depuis une fiche autorisée.</StatePanel>}
      <div className="pagination"><span>{query.data.count} opportunité(s) · page {page}</span><div><label>Lignes par page <select aria-label="Lignes par page" value={params.get('page_size')??'8'} onChange={e=>filter('page_size',e.target.value)}>{[8,20,50].map(n=><option key={n}>{n}</option>)}</select></label><Button disabled={!query.data.previous} onClick={()=>go(page-1)}>Précédent</Button><Button disabled={!query.data.next} onClick={()=>go(page+1)}>Suivant</Button></div></div>
    </>}
  </>;
}
