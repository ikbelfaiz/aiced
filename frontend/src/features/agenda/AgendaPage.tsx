import { useState } from 'react';
import { useQuery,useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { request,mutate } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { Button,StatePanel } from '../../components/ui';
import { DataEditor,type Field } from '../../components/DataEditor';

type Appointment={id:string;organization_id:string;title:string;kind:string;notes:string;starts_at:string;ends_at:string;version:number;can_edit:boolean};
type Agenda={count:number;next:string|null;previous:string|null;results:Appointment[];days:Record<string,number>;month:string;business_timezone:string;business_date:string};
type Context={organizations:{id:string;name:string}[];business_timezone:string;business_date:string};
const kinds:Record<string,string>={call:'Appel / relance',email:'Email à préparer',meeting:'Rendez-vous',visit:'Visite'};
function localParts(value:string,zone:string){const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));const get=(key:string)=>parts.find(p=>p.type===key)!.value;return {date:`${get('year')}-${get('month')}-${get('day')}`,time:`${get('hour')}:${get('minute')}`};}

export function AgendaPage(){
  const auth=useAuth();const cache=useQueryClient();const [params,setParams]=useSearchParams();
  const [editor,setEditor]=useState<Appointment|'new'|null>(null);
  const allowed=auth.can('clients.view')&&auth.can('interactions.view');
  const query=useQuery({queryKey:['agenda',auth.identity?.session.id,params.toString()],queryFn:({signal})=>request<Agenda>(`/api/agenda/?${params}`,{signal}),enabled:allowed,retry:false});
  const context=useQuery({queryKey:['agenda-context',auth.identity?.session.id],queryFn:({signal})=>request<Context>('/api/agenda/context/',{signal}),enabled:allowed,retry:false});
  function filter(key:string,value:string){const next=new URLSearchParams(params);next.delete('page');if(key==='month')next.delete('day');if(value)next.set(key,value);else next.delete(key);setParams(next);}
  const zone=query.data?.business_timezone??context.data?.business_timezone??'Africa/Tunis';
  if(!allowed)return <StatePanel kind="denied" title="Agenda non autorisé">Les habilitations clients et interactions sont requises.</StatePanel>;
  if(query.isError||context.isError)return <StatePanel kind="error" title="Agenda inaccessible" retry={()=>{void query.refetch();void context.refetch();}}>{query.error?.message??context.error?.message}</StatePanel>;
  if(query.isPending||context.isPending)return <StatePanel kind="loading" title="Chargement de l’agenda…"/>;
  const data=query.data;const month=data.month;
  const [year,monthNumber]=month.split('-').map(Number);
  const length=new Date(Date.UTC(year,monthNumber,0)).getUTCDate();
  const offset=(new Date(Date.UTC(year,monthNumber-1,1)).getUTCDay()+6)%7;
  const fields:Field[]=[...(editor==='new'?[{name:'organization_id',label:'Organisation',required:true,options:context.data.organizations.map(o=>({value:o.id,label:o.name}))}]:[]),
    {name:'title',label:'Titre',required:true,maxLength:160},{name:'kind',label:'Type d’activité',options:Object.entries(kinds).map(([value,label])=>({value,label}))},
    {name:'date',label:'Date du rendez-vous',type:'date',required:true},{name:'start_time',label:'Heure de début',type:'time',required:true},{name:'end_time',label:'Heure de fin',type:'time',required:true},
    {name:'notes',label:'Notes personnelles',type:'textarea',maxLength:5000}];
  const current=editor&&editor!=='new'?editor:null;
  const start=current?localParts(current.starts_at,zone):null;const end=current?localParts(current.ends_at,zone):null;
  return <>
    <div className="page-heading"><div><h1>Mon agenda</h1><p className="page-subtitle">Rendez-vous et activités planifiées personnels · {zone}</p></div><Button variant="primary" disabled={!context.data.organizations.length} onClick={()=>setEditor('new')}>Nouveau rendez-vous</Button></div>
    <p className="availability-note">Visible uniquement par son créateur. Chevauchements autorisés provisoirement. Aucune annulation, notification, invitation ou synchronisation ; les activités réalisées restent dans les fiches CRM.</p>
    <section className="card history-filters"><div className="history-filter-fields"><label>Mois<input aria-label="Mois" type="month" min="1900-01" max="9998-12" value={month} onChange={e=>filter('month',e.target.value)}/></label><Button variant="text" onClick={()=>filter('day','')}>Tout le mois</Button><Button variant="text" onClick={()=>{setParams({month:data.business_date.slice(0,7),day:data.business_date});}}>Aujourd’hui</Button><Button disabled title="Politique d’annulation à approuver par AMEN INVEST">Annulation indisponible</Button></div></section>
    <section className="card agenda-calendar" aria-label="Calendrier mensuel"><div className="agenda-grid">{['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'].map(day=><strong key={day}>{day}</strong>)}{Array.from({length:offset},(_,i)=><span key={'blank'+i}/>)}{Array.from({length},(_,i)=>{const day=`${month}-${String(i+1).padStart(2,'0')}`;return <button key={day} className={params.get('day')===day?'agenda-selected':''} aria-label={`${day} : ${data.days[day]??0} rendez-vous`} aria-pressed={params.get('day')===day} onClick={()=>filter('day',day)}><span>{i+1}</span><small>{data.days[day]??0}</small></button>;})}</div></section>
    <section className="card workspace-card"><h2>Liste chronologique{params.get('day')?` · ${params.get('day')}`:''}</h2><p className="muted">{data.count} rendez-vous dans la sélection ; calendrier calculé sur le mois complet, avant sélection du jour.</p>
    {!data.results.length?<StatePanel kind="empty" title="Aucun rendez-vous dans cette sélection"/>:<div className="workspace-activities">{data.results.map(item=>{const start=localParts(item.starts_at,zone),end=localParts(item.ends_at,zone);return <article key={item.id}><div><h3>{item.title}</h3><p>{start.date.split('-').reverse().join('/')} · {start.time}–{end.time} · {kinds[item.kind]}</p><p className="history-notes">{item.notes}</p></div>{item.can_edit&&<Button variant="text" onClick={()=>setEditor(item)} aria-label={`Modifier ${item.title}`}>Modifier</Button>}</article>;})}</div>}
    <div className="pagination"><span>Page {Number(params.get('page')??1)}</span><div><Button disabled={!data.previous} onClick={()=>{const next=new URLSearchParams(params);next.set('page',String(Number(params.get('page')??1)-1));setParams(next);}}>Précédent</Button><Button disabled={!data.next} onClick={()=>{const next=new URLSearchParams(params);next.set('page',String(Number(params.get('page')??1)+1));setParams(next);}}>Suivant</Button></div></div></section>
    {editor&&<DataEditor title={current?'Modifier un rendez-vous':'Nouveau rendez-vous'} description={`Heures locales ${zone}. Début et fin le même jour. Aucun participant ni rappel automatique.`} fields={fields} initial={{title:current?.title??'',kind:current?.kind??'meeting',notes:current?.notes??'',date:start?.date??params.get('day')??(data.business_date.startsWith(month)?data.business_date:month+'-01'),start_time:start?.time??'09:00',end_time:end?.time??'10:00'}} close={()=>setEditor(null)} save={async values=>{await mutate(current?`/api/agenda/${current.id}/`:'/api/agenda/',{...values,...(current?{version:current.version}:{})},current?'PATCH':'POST');await cache.invalidateQueries({queryKey:['agenda']});}}/>}
  </>;
}
