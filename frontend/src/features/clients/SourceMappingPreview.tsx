import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {z} from 'zod';
import {request} from '../../lib/api';
import {useAuth} from '../auth/AuthProvider';
import {Button,StatePanel} from '../../components/ui';

const scenarios:Record<string,string>={unique:'Candidat unique',ambiguous:'Correspondance ambiguë',missing:'Identifiant manquant',duplicate:'Identifiant dupliqué',multiple_accounts:'Plusieurs comptes pour un client fictif',conflicting_identifiers:'Références D / AH contradictoires'};
const statuses:Record<string,string>={candidate_unique:'Candidat unique — non approuvé',ambiguous_candidate:'Plusieurs candidats — aucun choix',missing_identifier:'Identifiant manquant — aucun lien',duplicate_identifier:'Doublon — aucun lien confirmé',conflicting_identifiers:'Références contradictoires — aucun lien'};
const synthetic=z.string().startsWith('SYNTH-');
const schema=z.object({mode:z.literal('synthetic'),mapping_approved:z.literal(false),real_source_access:z.literal(false),relationships_persisted:z.literal(false),dataset_version:synthetic,
  records:z.array(z.object({ref:synthetic,template:z.enum(['physical','legal','accounts']),source_id:synthetic.nullable().optional(),alternate_id:synthetic.nullable().optional(),account_id:synthetic.optional(),holder_D:synthetic.nullable().optional(),identifier_AH:synthetic.nullable().optional(),validation_status:z.enum(['synthetic_mapping_blocked','synthetic_technical_only']),provenance:z.object({dataset:synthetic,batch_reference:synthetic,row_number:z.number().int(),source_as_of:z.string(),digest:z.string().length(64),publication_state:z.literal('illustrative_fixture_not_a_published_import')})})).max(10),
  relationships:z.array(z.object({account_ref:synthetic,status:z.enum(['candidate_unique','ambiguous_candidate','missing_identifier','duplicate_identifier','conflicting_identifiers']),person_candidates:z.array(synthetic).max(10),fixture_client_candidates:z.array(synthetic).max(10),confirmed:z.literal(false)})).max(10)});

export function SourceMappingPreview({id,allowed}:{id:string;allowed:boolean}){
  const auth=useAuth();const [opened,setOpened]=useState(false),[scenario,setScenario]=useState('unique');
  const query=useQuery({queryKey:['source-mapping-preview',auth.identity?.session.id,id,scenario],queryFn:async({signal})=>schema.parse(await request(`/api/clients/${encodeURIComponent(id)}/source-mapping-preview/?scenario=${scenario}`,{signal})),enabled:allowed&&opened,retry:false,refetchOnWindowFocus:false});
  const data=allowed&&opened&&!query.isError?query.data:undefined;
  return <section className="card workspace-card" aria-label="Préparation du rapprochement source"><h2>Rapprochement source · préparation synthétique</h2>
    <p>Les données Excel réelles restent bloquées dans Client 360 : clés, propriété des champs et visibilité par objet doivent être approuvées par AMEN INVEST. Aucun client ni compte n’est créé ou rapproché ici.</p>
    <p>Cette démonstration indépendante utilise uniquement des identifiants fictifs. Le client fictif « SYNTH-CRM » ne désigne pas la fiche actuellement ouverte. Aucun nom, identifiant ou compte importé n’est consulté.</p>
    {!allowed?<p>La démonstration nécessite les habilitations client, financières et revue des imports.</p>:<><Button onClick={()=>{if(opened)void query.refetch();else setOpened(true);}}>Voir la démonstration synthétique</Button>{opened&&<label>Cas de rapprochement synthétique<select aria-label="Cas de rapprochement synthétique" value={scenario} onChange={e=>setScenario(e.target.value)}>{Object.entries(scenarios).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>}</>}
    {allowed&&opened&&query.isPending&&<StatePanel kind="loading" title="Chargement des exemples synthétiques…"/>}
    {allowed&&opened&&query.isError&&<StatePanel kind="error" title="Prévisualisation source indisponible" retry={()=>void query.refetch()}>Aucun candidat affiché. {query.error.message}</StatePanel>}
    {data&&<><p className="source-rule-notice">SYNTHÉTIQUE · {data.dataset_version} · hypothèse non approuvée : D du compte = B du tiers. AH et AC restent des références distinctes. Aucun rapprochement confirmé, aucune relation enregistrée.</p><div className="table-scroll"><table aria-label="Candidats synthétiques"><thead><tr><th>Compte source fictif</th><th>État</th><th>Tiers candidats fictifs</th><th>Clients CRM fictifs candidats</th></tr></thead><tbody>{data.relationships.map(row=><tr key={row.account_ref}><th>{row.account_ref}</th><td>{statuses[row.status]}</td><td>{row.person_candidates.join(', ')||'Aucun'}</td><td>{row.fixture_client_candidates.join(', ')||'Aucun'}</td></tr>)}</tbody></table></div>
    <details><summary>Identifiants, provenance et validation des exemples</summary><ul>{data.records.map(row=><li key={row.ref}><strong>{row.ref} · {row.template}</strong><p>Clé B : {row.source_id??'—'} · AC : {row.alternate_id??'—'} · compte E : {row.account_id??'—'} · détenteur D : {row.holder_D??'—'} · AH : {row.identifier_AH??'—'}</p><p>{row.validation_status==='synthetic_mapping_blocked'?'Rapprochement illustratif bloqué ; aucune obligation de champ métier déduite':'Validation technique illustrative uniquement, identité non approuvée'}. Lot fictif {row.provenance.batch_reference}, ligne {row.provenance.row_number}, situation {row.provenance.source_as_of}. Empreinte du jeu fictif : <code style={{overflowWrap:'anywhere'}}>{row.provenance.digest}</code>. Ce jeu versionné n’est pas un import publié.</p></li>)}</ul></details></>}
  </section>;
}
