import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {ArrowUpRight} from 'lucide-react';
import {CartesianGrid,Cell,Line,LineChart,Pie,PieChart,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';
import {z} from 'zod';
import {api,request} from '../../lib/api';
import {useAuth} from '../auth/AuthProvider';
import {formatNumber} from '../clients/model';
import {portfolioSchema} from '../reporting/ManagerialPortfolio';
import {PublishedImports} from './PublishedImports';

const count=z.number().int().nonnegative();
const activity=z.object({total:count,by_kind:z.record(z.string(),count),daily:z.array(z.object({date:z.string(),count}))});
const reportSchema=z.object({date_from:z.string(),date_to:z.string(),interactions:activity.nullable(),appointments:activity.nullable(),followups:z.object({overdue:count,today:count,upcoming:count,unscheduled:count}).nullable(),portfolio:portfolioSchema});
const pipelineSchema=z.object({count,statuses:z.object({open:count,won:count,lost:count})});
const campaignSchema=z.object({count});
const colors=['#2d8798','#e27162'];
const labels:Record<string,string>={call:'Appels',email:'Emails',meeting:'Rendez-vous',visit:'Visites'};
const dateLabel=(value:string)=>new Date(`${value}T12:00:00Z`).toLocaleDateString('fr-FR',{day:'numeric',month:'short',timeZone:'UTC'});

export function LiveDashboard(){
  const auth=useAuth(); const session=auth.identity?.session.id;
  const canClients=auth.can('clients.view');
  const canPipeline=canClients&&auth.can('opportunities.view');
  const clients=useQuery({queryKey:['dashboard-clients',session],queryFn:({signal})=>api.clients({pageSize:1},signal),enabled:canClients,retry:false});
  const report=useQuery({queryKey:['dashboard-managerial',session],queryFn:async({signal})=>reportSchema.parse(await request('/api/clients/managerial-report/',{signal})),enabled:canClients,retry:false});
  const pipeline=useQuery({queryKey:['dashboard-pipeline',session],queryFn:async({signal})=>pipelineSchema.parse(await request('/api/opportunities/?page_size=1',{signal})),enabled:canPipeline,retry:false});
  const campaigns=useQuery({queryKey:['dashboard-campaigns',session],queryFn:async({signal})=>campaignSchema.parse(await request('/api/campaigns/?page_size=1',{signal})),enabled:canPipeline,retry:false});
  const portfolio=!report.isError?report.data?.portfolio:undefined;
  const activities=!report.isError?report.data?.interactions:undefined;
  const followups=!report.isError?report.data?.followups:undefined;
  const statuses=!pipeline.isError?pipeline.data?.statuses:undefined;
  const clientCount=canClients&&!clients.isError?clients.data?.count:undefined;
  const unavailable=(allowed:boolean,error:boolean)=>!allowed?'Accès non autorisé':error?'Données indisponibles':'Chargement…';
  const clientText=clientCount===undefined?unavailable(canClients,clients.isError):'Clients accessibles · hors prospects';
  const reportText=!canClients?'Accès non autorisé':report.isError?'Source indisponible':report.isPending?'Chargement…':'Aucune habilitation correspondante';
  const segments=portfolio?[{name:'Personnes physiques',value:portfolio.by_kind.physical},{name:'Personnes morales',value:portfolio.by_kind.legal}]:[];
  const total=segments.reduce((sum,row)=>sum+row.value,0);
  const bars=statuses?[{label:'Ouvertes',value:statuses.open},{label:'Gagnées',value:statuses.won},{label:'Perdues',value:statuses.lost}]:[];
  const maxBar=Math.max(1,...bars.map(row=>row.value));
  const activityPeriod=report.data?`${dateLabel(report.data.date_from)} – ${dateLabel(report.data.date_to)}`:'30 derniers jours';
  const kindEntries=activities?Object.entries(activities.by_kind).map(([key,value])=>({name:labels[key]??key,value})):[];
  const refresh=()=>{if(canClients){void clients.refetch();void report.refetch();}if(canPipeline){void pipeline.refetch();void campaigns.refetch();}};
  return <>
    <div className="page-heading"><div><p className="page-eyebrow">AICED · PILOTAGE</p><h1>Tableau de bord</h1><p className="page-subtitle">Voici l’essentiel de votre activité dans votre périmètre autorisé.</p></div><div className="heading-actions"><button type="button" className="button" onClick={refresh}>Actualiser</button><Link className="button" to="/activite-commerciale">Voir l’activité</Link></div></div>
    <section className="primary-metrics" aria-label="Indicateurs principaux">
      <article className="card metric-card" aria-label="Clients accessibles"><p>Clients accessibles</p><strong>{clientCount===undefined?'—':formatNumber(clientCount)}</strong><span className="muted">{clientText}</span></article>
      <article className="card metric-card"><p>Opportunités ouvertes</p><strong>{statuses?formatNumber(statuses.open):'—'}</strong><span className="muted">{statuses?'Statut actuel · toutes dates':unavailable(canPipeline,pipeline.isError)}</span></article>
      <article className="card metric-card"><p>Encours</p><strong>—</strong><span className="muted">Valorisations financières indisponibles</span></article>
      <article className="card metric-card"><p>Taux de rétention</p><strong>—</strong><span className="muted">Méthode de calcul non approuvée</span></article>
    </section>
    <section className="secondary-metrics" aria-label="Suivi de l’activité">
      {[{title:'Interactions enregistrées',value:activities?.total,caption:activityPeriod,to:'/interactions'}, {title:'Relances à échéance',value:followups?followups.overdue+followups.today:undefined,caption:'En retard ou aujourd’hui',to:'/prospects/relances'}, {title:'Brouillons de campagnes',value:!campaigns.isError?campaigns.data?.count:undefined,caption:'Mes brouillons personnels',to:'/campagnes'}, {title:'Mes rendez-vous',value:report.isError?undefined:report.data?.appointments?.total,caption:activityPeriod,to:'/agenda'}].map(item=><article className="card small-metric" key={item.title}><p>{item.title}</p><div><strong>{item.value===undefined?'—':formatNumber(item.value)}</strong><span>{item.value===undefined?(item.title.includes('campagnes')?unavailable(canPipeline,campaigns.isError):reportText):item.caption}</span><Link to={item.to} aria-label={`Consulter : ${item.title}`}><ArrowUpRight size={18}/></Link></div></article>)}
    </section>
    <div className="dashboard-charts">
      <section className="card trend-card"><h2>Évolution des interactions</h2><p className="card-subtitle">{activities?`${activityPeriod} · interactions enregistrées` : reportText}</p>{activities?<><div className="trend-plot" role="img" aria-label="Graphique des interactions enregistrées par jour"><ResponsiveContainer width="100%" height="100%"><LineChart data={activities.daily} margin={{top:12,right:12,left:-25,bottom:8}}><CartesianGrid stroke="#e1e5ee" vertical={false}/><XAxis dataKey="date" tickFormatter={dateLabel} minTickGap={35} tick={{fontSize:10}}/><YAxis allowDecimals={false} tick={{fontSize:10}}/><Tooltip labelFormatter={value=>dateLabel(String(value))}/>      <Line type="monotone" dataKey="count" name="Interactions" stroke="#2d8798" strokeWidth={3} dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div><details><summary>Voir les valeurs</summary><ul>{activities.daily.map(day=><li key={day.date}>{dateLabel(day.date)} : {day.count}</li>)}</ul></details></>:<p className="availability-note">Les interactions ne sont pas disponibles dans votre périmètre.</p>}</section>
      <section className="card segment-card"><h2>Répartition des clients par type</h2><p className="card-subtitle">Clients accessibles · hors prospects</p>{portfolio?<div className="segment-body"><div className="segment-donut" role="img" aria-label={`Répartition : ${segments[0].value} personnes physiques, ${segments[1].value} personnes morales`}><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={segments} dataKey="value" innerRadius="73%" outerRadius="99%" startAngle={90} endAngle={-270} stroke="white" isAnimationActive={false}>{segments.map((segment,index)=><Cell key={segment.name} fill={colors[index]}/>)}</Pie></PieChart></ResponsiveContainer><div><strong>{formatNumber(total)}</strong><span>TOTAL</span></div></div><ul className="segment-legend">{segments.map((segment,index)=><li key={segment.name}><span><i style={{background:colors[index]}}/>{segment.name}</span><strong>{formatNumber(segment.value)}</strong></li>)}</ul></div>:<p className="availability-note">{reportText}</p>}<p className="availability-note">La segmentation métier de la maquette n’est pas encore définie.</p></section>
    </div>
    <div className="dashboard-bottom">
      <section className="card pipeline-card" aria-label="Opportunités actuelles"><h2>Pipeline des opportunités</h2><p className="card-subtitle">{statuses?`${formatNumber(pipeline.data!.count)} opportunité(s) · statuts actuels`:unavailable(canPipeline,pipeline.isError)}</p>{statuses&&<div className="pipeline-bars">{bars.map(bar=><div key={bar.label}><p>{bar.label}<strong> · {formatNumber(bar.value)}</strong></p><i style={{width:`${100*bar.value/maxBar}%`}}/></div>)}</div>}<Link className="text-link" to="/opportunites">Consulter le pipeline</Link></section>
      <section className="card activity-card"><h2>Activité par type</h2><p className="card-subtitle">{activities?`${activities.total} interactions · ${activityPeriod}`:reportText}</p>{activities&&<ul className="segment-legend">      {kindEntries.map((entry,index)=><li key={entry.name}><span><i style={{background:index%2?'#e27162':'#2d8798'}}/>{entry.name}</span><strong>{entry.value}</strong></li>)}</ul>}<Link className="text-link" to="/activite-commerciale">Détail de l’activité</Link></section>
      <section className="card priorities-card"><div className="card-title-row"><h2>Relances prospects</h2><Link className="text-link" to="/prospects/relances">Tout voir</Link></div><p className="card-subtitle">Échéances manuelles · situation actuelle</p>{followups?<div className="priority-list">{[['En retard',followups.overdue],['Aujourd’hui',followups.today],['À venir',followups.upcoming],['Sans date',followups.unscheduled]].map(([label,value])=><div key={String(label)}><p>{label}<strong>{value}</strong></p></div>)}</div>:<p className="availability-note">{reportText}</p>}<p className="availability-note">Les échéances comprennent tous les statuts, y compris clos.</p></section>
    </div>
    <PublishedImports/>
  </>;
}
