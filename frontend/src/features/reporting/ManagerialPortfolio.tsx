import {z} from 'zod';
import {Link} from 'react-router-dom';
import {Bar,BarChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';

const count=z.number().int().nonnegative();
export const portfolioSchema=z.object({by_kind:z.object({physical:count,legal:count}),quality:z.object({
  total:count,complete:count.nullable(),incomplete:count.nullable(),available:z.boolean(),provisional:z.boolean(),
  definition:z.string(),fields:z.array(z.object({key:z.string(),label:z.string()})).max(4),missing_counts:z.record(z.string(),count)})});

export function OperationalBars({title,values}:{title:string;values:{name:string;count:number}[]}){
  return <section className="card workspace-card" aria-label={title}><h2>{title}</h2>
    <div className="report-chart" role="img" aria-label={`Graphique : ${title}`}><ResponsiveContainer width="100%" height="100%"><BarChart data={values} layout="vertical" margin={{left:8,right:24}}><CartesianGrid strokeDasharray="3 3"/><XAxis type="number" allowDecimals={false}/><YAxis type="category" dataKey="name" width={115}/><Tooltip/><Bar dataKey="count" name="Enregistrements" fill="#1d4695" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <details><summary>Valeurs : {title}</summary><table aria-label={`Valeurs : ${title}`}><thead><tr><th>Catégorie</th><th>Nombre</th></tr></thead><tbody>{values.map(row=><tr key={row.name}><th>{row.name}</th><td>{row.count}</td></tr>)}</tbody></table></details>
    {!values.some(row=>row.count>0)&&<p className="muted">Aucun enregistrement dans ce périmètre.</p>}
  </section>;
}

export function ManagerialPortfolio({portfolio}:{portfolio:z.infer<typeof portfolioSchema>}){
  const quality=portfolio.quality;
  return <section aria-label="Portefeuille CRM actuel">
    <h2>Portefeuille actuel · indépendant de la période</h2>
    <div className="report-grid"><section className="card workspace-card" aria-label="Clients autorisés"><h3>Clients accessibles</h3><strong className="report-total">{quality.total}</strong><p>Hors prospects, après autorisation objet. Aucun total global implicite.</p><Link className="text-link" to="/clients">Consulter les clients</Link></section>
      <section className="card workspace-card" aria-label="Profils complets"><h3>Profils techniquement complets</h3><strong className="report-total">{quality.available?quality.complete:'Non calculable'}</strong><p>{quality.available?`${quality.incomplete} profil(s) incomplet(s)`:'Aucun champ technique configuré.'}</p><p className="muted">{quality.definition}</p></section></div>
    <div className="report-grid"><OperationalBars title="Clients par type" values={[{name:'Physiques',count:portfolio.by_kind.physical},{name:'Morales',count:portfolio.by_kind.legal}]}/>
    {quality.available&&<OperationalBars title="Champs CRM absents" values={quality.fields.map(field=>({name:field.label,count:quality.missing_counts[field.key]}))}/>}</div>
    <p className="availability-note">Présence technique provisoire uniquement, sans score métier ni contrôle KYC. Les absences par champ peuvent concerner le même profil ; elles ne s’additionnent pas en nombre de clients. Aucun historique de complétude n’est déduit.</p>
  </section>;
}
