import {z} from 'zod';
import {Link} from 'react-router-dom';
import {Bar,BarChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';

const count=z.number().int().nonnegative();
export const portfolioSchema=z.object({by_kind:z.object({physical:count,legal:count}),quality:z.object({
  total:count,complete:count.nullable(),incomplete:count.nullable(),available:z.boolean(),provisional:z.boolean(),
  definition:z.string(),fields:z.array(z.object({key:z.string(),label:z.string()})).max(4),missing_counts:z.record(z.string(),count)}),
  team:z.array(z.object({membership_id:z.string(),username:z.string(),organization:z.string(),clients:count,interactions:count.nullable()})).optional()});

export function OperationalBars({title,values}:{title:string;values:{name:string;count:number}[]}){
  return <section className="card workspace-card" aria-label={title}><h2>{title}</h2>
    <div className="report-chart" role="img" aria-label={`Graphique : ${title}`}><ResponsiveContainer width="100%" height="100%"><BarChart data={values} layout="vertical" margin={{left:8,right:24}}><CartesianGrid strokeDasharray="3 3"/><XAxis type="number" allowDecimals={false}/><YAxis type="category" dataKey="name" width={115}/><Tooltip/><Bar dataKey="count" name="Enregistrements" fill="#2d8798" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <details><summary>Valeurs : {title}</summary><table aria-label={`Valeurs : ${title}`}><thead><tr><th>Catégorie</th><th>Nombre</th></tr></thead><tbody>{values.map(row=><tr key={row.name}><th>{row.name}</th><td>{row.count}</td></tr>)}</tbody></table></details>
    {!values.some(row=>row.count>0)&&<p className="muted">Aucun enregistrement dans ce périmètre.</p>}
  </section>;
}

export function ManagerialPortfolio({portfolio}:{portfolio:z.infer<typeof portfolioSchema>}){
  const quality=portfolio.quality;
  return <section className="managerial-overview" aria-label="Portefeuille CRM actuel">
    <div className="managerial-section-heading"><div><p>Vue d’équipe</p><h2>Portefeuille actuel</h2></div><span>Indépendant de la période</span></div>
    <div className="managerial-kpis"><section className="managerial-kpi managerial-kpi-primary" aria-label="Clients autorisés"><span>Clients accessibles</span><strong>{quality.total}</strong><p>Hors prospects, après autorisation objet.</p><Link className="text-link" to="/clients">Consulter les clients</Link></section>
      <section className="managerial-kpi" aria-label="Profils complets"><span>Profils complets</span><strong>{quality.available?quality.complete:'—'}</strong><p>{quality.available?`${quality.incomplete} profil(s) incomplet(s)`:'Champ technique non configuré.'}</p></section>
      <section className="managerial-kpi" aria-label="Personnes physiques"><span>Personnes physiques</span><strong>{portfolio.by_kind.physical}</strong><p>Clients accessibles.</p></section>
      <section className="managerial-kpi" aria-label="Personnes morales"><span>Personnes morales</span><strong>{portfolio.by_kind.legal}</strong><p>Clients accessibles.</p></section></div>
    {portfolio.team&&portfolio.team.length>0&&<section className="card managerial-team" aria-label="Vue des commerciaux"><div className="managerial-section-heading"><div><p>Équipe commerciale</p><h2>Portefeuille par collaborateur</h2></div><span>{portfolio.team.length} membre(s)</span></div><div className="managerial-team-table"><table aria-label="Activité des commerciaux"><thead><tr><th>Commercial</th><th>Organisation</th><th>Dossiers clients</th><th>Interactions période</th></tr></thead><tbody>{portfolio.team.map(member=><tr key={member.membership_id}><th>{member.username}</th><td>{member.organization}</td><td>{member.clients}</td><td>{member.interactions??'Accès restreint'}</td></tr>)}</tbody></table></div></section>}
    <div className="report-grid"><OperationalBars title="Clients par type" values={[{name:'Physiques',count:portfolio.by_kind.physical},{name:'Morales',count:portfolio.by_kind.legal}]}/>
    {quality.available&&<OperationalBars title="Champs CRM absents" values={quality.fields.map(field=>({name:field.label,count:quality.missing_counts[field.key]}))}/>}</div>
    <p className="availability-note">Présence technique provisoire uniquement, sans score métier ni contrôle KYC. Les absences par champ peuvent concerner le même profil ; elles ne s’additionnent pas en nombre de clients. Aucun historique de complétude n’est déduit.</p>
  </section>;
}
