import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { request } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { Badge, Button, StatePanel } from '../../components/ui';
import { Plus,Search } from 'lucide-react';

const historySchema = z.object({
  count: z.number(), next: z.string().nullable(), previous: z.string().nullable(),
  results: z.array(z.object({id:z.string(),party_id:z.string(),party_name:z.string(),is_prospect:z.boolean(),
    kind:z.string(),subject:z.string(),notes:z.string(),occurred_at:z.string(),author_id:z.string(),author_name:z.string(),version:z.number()})),
});
const kinds: Record<string,string> = {call:'Appel',email:'Email',meeting:'Réunion / rendez-vous réalisé',visit:'Visite'};
const date = (value:string) => new Date(value).toLocaleString('fr-FR',{timeZone:'Africa/Tunis',dateStyle:'short',timeStyle:'short'});
const reportSchema=z.object({date_from:z.string(),date_to:z.string(),interactions:z.object({total:z.number(),by_kind:z.record(z.string(),z.number())}).nullable()});

export function InteractionHistory() {
  const auth=useAuth();
  const [params,setParams]=useSearchParams();
  const [draft,setDraft]=useState(params.get('search')??'');
  const allowed=auth.can('clients.view')&&auth.can('interactions.view');
  const page=Math.max(1,Number(params.get('page'))||1);
  const size=Number(params.get('page_size'))||8;
  const query=useQuery({
    queryKey:['interaction-history',auth.identity?.session.id,params.toString()],
    queryFn:async({signal})=>historySchema.parse(await request(`/api/interactions/?${params}`,{signal})),
    enabled:allowed,retry:false,
  });
  const report=useQuery({queryKey:['history-summary',auth.identity?.session.id],queryFn:async({signal})=>reportSchema.parse(await request('/api/clients/activity-report/',{signal})),enabled:allowed,retry:false});
  function filter(key:string,value:string){
    const next=new URLSearchParams(params); next.delete('page');
    if(value)next.set(key,value);else next.delete(key);
    setParams(next);
  }
  function go(value:number){const next=new URLSearchParams(params);next.set('page',String(value));setParams(next);}
  if(!allowed)return <StatePanel kind="denied" title="Historique des interactions non autorisé">Les habilitations clients et interactions sont requises.</StatePanel>;
  return <>
    <div className="page-heading"><div><p className="page-eyebrow">AMEN INVEST · AICED</p>
      <h1>Historique des interactions</h1><p className="page-subtitle">Retrouvez les échanges enregistrés avec les clients et prospects de votre périmètre.</p>
    </div><Link className="button button-primary" to="/clients"><Plus size={16}/>Ajouter depuis une fiche</Link></div>
    <section className="primary-metrics interaction-metrics" aria-label="Synthèse des interactions">{[{label:'Interactions enregistrées',value:report.data?.interactions?.total},{label:'Appels',value:report.data?.interactions?.by_kind.call},{label:'Emails',value:report.data?.interactions?.by_kind.email},{label:'Rendez-vous et visites',value:report.data?.interactions?((report.data.interactions.by_kind.meeting??0)+(report.data.interactions.by_kind.visit??0)):undefined}].map(item=><article className="card metric-card" key={item.label}><p>{item.label}</p><strong>{report.isError||item.value===undefined?'—':item.value}</strong><span className="muted">{report.isError?'Source indisponible':report.data?`${report.data.date_from.split('-').reverse().join('/')} – ${report.data.date_to.split('-').reverse().join('/')} · périmètre autorisé`:'Chargement…'}</span></article>)}</section>
    <section className="client-filters history-filters" aria-label="Filtres des interactions">
      <form onSubmit={e=>{e.preventDefault();filter('search',draft);}} className="history-search">
        <label className="sr-only" htmlFor="history-search">Rechercher par client, objet ou compte rendu</label>
        <div><div className="pipeline-search-input"><Search size={16}/><input id="history-search" placeholder="Rechercher par client, objet ou compte rendu…" value={draft} maxLength={200} onChange={e=>setDraft(e.target.value)}/></div><Button type="submit">Rechercher</Button></div>
      </form>
      <div className="history-filter-fields">
        <label>Type d’interaction<select aria-label="Type d’interaction" value={params.get('kind')??''} onChange={e=>filter('kind',e.target.value)}><option value="">Tous les types</option>{Object.entries(kinds).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
        <label>Depuis le<input type="date" value={params.get('date_from')??''} onChange={e=>filter('date_from',e.target.value)}/></label>
        <label>Jusqu’au<input type="date" value={params.get('date_to')??''} onChange={e=>filter('date_to',e.target.value)}/></label>
        <Button variant="text" onClick={()=>{setDraft('');setParams({});}}>Réinitialiser les filtres</Button>
      </div>
      <p className="muted">Dates en heure de Tunis. L’auteur désigne la personne ayant enregistré l’échange. Les résultats et prochaines actions ne sont pas déduits des notes.</p>
    </section>
    {query.isPending?<StatePanel kind="loading" title="Chargement des interactions…"/>:
      query.isError?<StatePanel kind="error" title="Impossible de charger les interactions" retry={()=>void query.refetch()}>{query.error.message}</StatePanel>:
      !query.data.results.length?<StatePanel kind="empty" title="Aucune interaction dans cette sélection">Modifiez vos filtres ou enregistrez un échange depuis une fiche autorisée.</StatePanel>:
      <div className="client-table-card"><div className="table-scroll" tabIndex={0} aria-label="Tableau des interactions"><table className="history-table">
        <thead><tr>{['Client / prospect','Type','Auteur','Date','Objet et compte rendu','Fiche'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{query.data.results.map(row=><tr key={row.id}>
          <th scope="row">{row.party_name}<span className="client-reference">{row.is_prospect?'Prospect AICED':'Client'} · Identifiant interne {row.party_id.slice(0,8)}</span></th>
          <td><Badge tone="blue">{kinds[row.kind]??row.kind}</Badge></td><td>{row.author_name}</td><td><time dateTime={row.occurred_at}>{date(row.occurred_at)}</time></td>
          <td><strong>{row.subject}</strong>{row.notes&&<details><summary>Lire le compte rendu</summary><p className="history-notes">{row.notes}</p></details>}</td>
          <td><Link className="text-link" to={`/clients/${row.party_id}?onglet=interactions`}>Ouvrir la fiche de {row.party_name}</Link></td>
        </tr>)}</tbody>
      </table></div><div className="pagination"><span>{query.data.count} interaction(s) · page {page}</span><div>
        <label>Lignes par page <select value={size} onChange={e=>filter('page_size',e.target.value)}>{[8,20,50].map(n=><option key={n}>{n}</option>)}</select></label>
        <Button disabled={!query.data.previous} onClick={()=>go(page-1)}>Précédent</Button><Button disabled={!query.data.next} onClick={()=>go(page+1)}>Suivant</Button>
      </div></div></div>}
  </>;
}
