import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link,useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { request } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { Button,StatePanel } from '../../components/ui';
import { CalendarDays,Plus,Search,ArrowUpRight } from 'lucide-react';

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
    <div className="page-heading"><div><p className="page-eyebrow">AMEN INVEST · AICED</p><h1>Pipeline des opportunités</h1><p className="page-subtitle">Pilotez les échanges commerciaux dans votre périmètre autorisé.</p></div><Link to="/clients" className="button button-primary"><Plus size={16}/>Nouvelle opportunité</Link></div>
    <section className="pipeline-filters" aria-label="Filtres du pipeline"><form className="pipeline-search" onSubmit={e=>{e.preventDefault();filter('search',draft);}}><label className="sr-only" htmlFor="pipeline-search">Rechercher par dossier, titre ou notes</label><div className="pipeline-search-input"><Search size={16}/><input id="pipeline-search" placeholder="Rechercher une opportunité…" value={draft} maxLength={200} onChange={e=>setDraft(e.target.value)}/></div><Button type="submit">Rechercher</Button></form>
      <div className="pipeline-filter-fields"><label><span className="sr-only">Statut</span><select aria-label="Statut" value={params.get('status')??''} onChange={e=>filter('status',e.target.value)}><option value="">Tous les statuts</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <label>Trier par<select aria-label="Trier par" value={params.get('ordering')??'-updated_at'} onChange={e=>filter('ordering',e.target.value)}><option value="-updated_at">Modification récente</option><option value="updated_at">Modification ancienne</option><option value="title">Titre A–Z</option><option value="-title">Titre Z–A</option><option value="due_date">Échéance croissante</option><option value="-due_date">Échéance décroissante</option></select></label>
      <Button variant="text" onClick={()=>{setDraft('');setParams({});}}>Réinitialiser les filtres</Button></div>
      </section>
    {query.isPending?<StatePanel kind="loading" title="Chargement du pipeline…"/>:query.isError?<StatePanel kind="error" title="Impossible de charger le pipeline" retry={()=>void query.refetch()}>{query.error.message}</StatePanel>:<>
      <div className="pipeline-summary"><p>{query.data.count} opportunité(s) dans la sélection · {query.data.statuses.open??0} ouvertes avant filtre de statut</p><span>Montants estimés · suivi commercial uniquement</span></div>
      <div className="opportunity-board">{Object.entries(statuses).filter(([key])=>!params.get('status')||params.get('status')===key).map(([status,label])=><section className={`pipeline-column pipeline-column-${status}`} aria-label={label} key={status}><div className="pipeline-column-heading"><h2>{label} <span className="sr-only">({query.data.statuses[status]})</span></h2><span className="pipeline-count" aria-hidden="true">{query.data.statuses[status]}</span></div><p className="pipeline-column-caption">Statut actuel · tous les résultats</p>
        {query.data.results.filter(row=>row.status===status).map(row=><article className="pipeline-card" key={row.id}><div className="pipeline-card-top"><span className="pipeline-badge">Commercial</span><Link className="pipeline-open-icon" aria-label={`${row.can_edit?'Ouvrir / modifier':'Ouvrir'} : ${row.title}`} to={`/clients/${row.party_id}?onglet=opportunities&opportunite=${row.id}`}><ArrowUpRight size={17}/></Link></div><h3>{row.party_name}</h3><p className="pipeline-card-title">{row.title}</p><p className="pipeline-card-amount">{row.amount===null?'Estimation non renseignée':`${row.amount} ${row.currency}`}</p>{row.notes&&<details className="pipeline-card-notes"><summary>Lire les notes</summary><p className="history-notes">{row.notes}</p></details>}<div className="pipeline-card-date"><CalendarDays size={14}/><span>{row.due_date?row.due_date.split('-').reverse().join('/'):'Échéance non renseignée'}</span></div></article>)}
        {!query.data.results.some(row=>row.status===status)&&<p className="pipeline-empty">Aucune carte sur cette page.</p>}</section>)}</div>
      <p className="pipeline-board-note">Cartes de la page courante · compteurs sur les résultats autorisés après recherche et avant filtre de statut · estimations commerciales déclarées.</p>
      {!query.data.count&&<StatePanel kind="empty" title="Aucune opportunité dans cette sélection">Modifiez les filtres ou créez une opportunité depuis une fiche autorisée.</StatePanel>}
      <div className="pagination"><span>{query.data.count} opportunité(s) · page {page}</span><div><label>Lignes par page <select aria-label="Lignes par page" value={params.get('page_size')??'8'} onChange={e=>filter('page_size',e.target.value)}>{[8,20,50].map(n=><option key={n}>{n}</option>)}</select></label><Button disabled={!query.data.previous} onClick={()=>go(page-1)}>Précédent</Button><Button disabled={!query.data.next} onClick={()=>go(page+1)}>Suivant</Button></div></div>
    </>}
  </>;
}
