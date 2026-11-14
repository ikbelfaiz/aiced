import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { CreateClient } from './CreateClient';
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, Download, Plus, Search } from 'lucide-react';
import { api } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { useDesignPreview } from '../useDesignPreview';
import { previewClients } from '../design-preview';
import { Badge, Button, Dialog, StatePanel } from '../../components/ui';
import { formatNumber, toClientRow, type ClientRow } from './model';

function ClientDialog({ row, close }: { row: ClientRow; close: () => void }) {
  return <Dialog title="Exemple de maquette" onClose={close}><Badge tone="amber">Exemple fictif · aucun dossier API</Badge><h3 className="mt-5 font-semibold">{row.name}</h3><p className="muted mt-2">Ce client illustre uniquement le PDF de référence. Ouvrez un dossier API pour consulter la vue Client 360°.</p></Dialog>;
}

export function ClientsPage() {
  const auth = useAuth();
  const preview = useDesignPreview();
  const [params, setParams] = useSearchParams();
  const search = params.get('recherche') ?? '';
  const kind = params.get('type') ?? '';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const pageSize = [8, 16, 24].includes(Number(params.get('taille'))) ? Number(params.get('taille')) : 8;
  const [draft, setDraft] = useState(search);
  const [selected, setSelected] = useState<ClientRow | null>(null);
  const [creating,setCreating]=useState(false);
  const update = (key: string, value: string) => setParams((previous) => {
    const next = new URLSearchParams(previous);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== 'page') next.delete('page');
    return next;
  }, { replace: true });
  useEffect(() => { setDraft(search); }, [search]);
  useEffect(() => {
    if (draft === search) return;
    const timer = window.setTimeout(() => update('recherche', draft), 300);
    return () => window.clearTimeout(timer);
  }, [draft, search]);
  const clients = useQuery({ queryKey: ['clients', auth.identity?.session.id, search, kind, page, pageSize], queryFn: ({ signal }) => api.clients({ search, kind, page, pageSize }, signal), enabled: !preview, retry: false });
  const filteredExamples = previewClients.filter((row) => (!kind || row.kind === kind) && row.name.toLocaleLowerCase('fr').includes(search.toLocaleLowerCase('fr')));
  const rows = preview ? filteredExamples.slice((page - 1) * pageSize, page * pageSize) : clients.data?.results.map(toClientRow) ?? [];
  const count = preview ? filteredExamples.length : clients.data?.count ?? 0;
  const pages = Math.max(1, Math.ceil(count / pageSize));
  function reset() { setDraft(''); setParams(preview ? { apercu: 'maquette' } : {}); }
  const financial = auth.can('clients.view_financial');
  return <>
    <div className="page-heading"><div><p className="page-eyebrow">AMEN INVEST · AICED</p><h1>Panorama Clients</h1><p className="page-subtitle">Une vision consolidée de vos clients, de leurs investissements et de leur potentiel.</p></div><div className="heading-actions"><Button disabled title="L’export n’est pas disponible"><Download size={17} />Exporter</Button><Button variant="primary" disabled={preview||!auth.can('clients.create')} title="Création locale AICED avec habilitation explicite" onClick={()=>setCreating(true)}><Plus size={18} />Nouveau client</Button></div></div>
    <section className="portfolio-metrics" aria-label="Synthèse du portefeuille"><article className="card"><span>{search || kind ? 'Clients correspondants' : 'Clients du portefeuille'}</span><strong>{preview && !search && !kind ? '1 248' : clients.isPending && !preview ? '—' : formatNumber(count)}</strong></article><article className="card"><span>Encours total</span><strong>{preview ? '82,4 M TND' : '—'}</strong></article><article className="card"><span>Potentiel élevé</span><strong className={preview ? 'positive' : 'unavailable-value'}>{preview ? '186 clients' : 'Non calculé'}</strong></article></section>
    <section className="card filter-card" aria-label="Recherche et filtres clients"><form onSubmit={(event) => { event.preventDefault(); update('recherche', draft); }} className="input-with-icon client-search"><Search size={18} /><input aria-label="Rechercher un client" placeholder="Rechercher par nom ou identifiant AICED…" value={draft} onChange={(event) => setDraft(event.target.value)} /></form>
      <div className="filter-row"><label className="select-wrap"><span className="sr-only">Type de personne</span><select aria-label="Type de personne" value={kind} onChange={(event) => update('type', event.target.value)}><option value="">Type de personne</option><option value="physical">Personne physique</option><option value="legal">Personne morale</option></select><ChevronDown size={14} /></label>{['Âge', 'Secteur', 'Revenus', 'Profil de risque', 'Produit', 'Montant investi', 'Segment client'].map((filter) => <button key={filter} className="filter-button" disabled title="Ce critère n’est pas encore disponible">{filter}<ChevronDown size={14} /></button>)}</div>
      <div className="filter-summary"><span>{search || kind ? 'Filtres appliqués · recherche dans votre périmètre autorisé' : 'Tous les clients · Aucun filtre appliqué'}</span><button className="text-link" onClick={reset}>Réinitialiser les filtres</button></div>
    </section>
    <div className="directory-heading"><h2>Répertoire clients</h2><p>{preview ? 'Maquette de référence · aucune synchronisation réelle' : 'Consultation du périmètre autorisé · source Carthago non connectée'}</p></div>
    {!preview && clients.isPending ? <div className="card"><StatePanel kind="loading" title="Chargement des clients…" /></div> : !preview && clients.isError ? <div className="card"><StatePanel kind="error" title="Impossible de charger les clients" retry={() => void clients.refetch()}>{clients.error.message}</StatePanel><div className="state-actions"><Button onClick={reset}>Réinitialiser la recherche</Button><Button onClick={() => void auth.refresh()}>Actualiser mes droits</Button></div></div> : rows.length === 0 ? <div className="card"><StatePanel kind="empty" title={search || kind ? 'Aucun client ne correspond à votre recherche' : 'Aucun client dans votre périmètre'}>Modifiez les filtres ou contactez votre responsable pour vérifier vos affectations.</StatePanel>{(search || kind) && <div className="state-actions"><Button onClick={reset}>Réinitialiser les filtres</Button></div>}</div> : <div className="client-table-card">
      <div className="table-scroll" tabIndex={0} aria-label="Tableau clients, défilement horizontal si nécessaire"><table><caption className="sr-only">Répertoire des clients accessibles{preview ? ' — données fictives de maquette' : ''}</caption><colgroup>{[18, 10, 10, 11, 12, 8, 11, 10, 8].map((width, i) => <col key={i} style={{ width: `${width}%` }} />)}</colgroup><thead><tr>{['Client', 'Segment', 'Profil de risque', 'Total investi', 'Produits', 'Score de potentiel', 'Dernière interaction', 'Statut', 'Fiche'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.id}>
        <th scope="row"><strong>{row.name}</strong><span className="client-reference" title={row.backendId}>{row.reference}</span></th>
        <td>{row.segment ? <Badge tone={row.segment === 'VIP' ? 'blue' : 'neutral'}>{row.segment}</Badge> : <span className="muted">Non renseigné</span>}</td><td>{row.risk ?? '—'}</td>
        <td>{row.invested !== undefined && financial ? <><strong>{formatNumber(row.invested)}</strong><span className="client-reference">TND</span></> : <span className="muted" title={financial ? 'Les encours ne sont pas disponibles' : 'Habilitation financière requise'}>{financial ? '—' : 'Accès restreint'}</span>}</td>
        <td>{row.products ?? '—'}</td><td>{row.score !== undefined ? <Badge tone={row.score >= 80 ? 'green' : 'amber'}>{row.score} / 100</Badge> : <span className="muted">Non calculé</span>}</td><td>{row.interaction ?? '—'}</td><td>{row.status ? <Badge tone={row.status === 'Actif' ? 'green' : 'amber'}>{row.status}</Badge> : <span className="muted">Non renseigné</span>}</td>
        <td>{row.backendId?<Link className="text-link client-detail-link" to={`/clients/${row.backendId}`} aria-label={`Voir la fiche de ${row.name}`}>Voir fiche <ArrowRight size={13}/></Link>:<button className="text-link client-detail-link" onClick={() => setSelected(row)} aria-label={`Voir la fiche de ${row.name}`}>Voir fiche <ArrowRight size={13} /></button>}</td>
      </tr>)}</tbody></table></div>
      <div className="pagination"><span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, count)} sur {formatNumber(count)} {preview ? 'exemples de maquette' : 'résultats'}</span><div><label>Lignes par page : <select aria-label="Lignes par page" value={pageSize} onChange={(event) => update('taille', event.target.value)}>{[8, 16, 24].map((size) => <option key={size}>{size}</option>)}</select></label><button className="page-button" aria-label="Page précédente" disabled={page <= 1} onClick={() => update('page', String(page - 1))}><ChevronLeft size={17} /></button><span className="current-page" aria-current="page">{page}</span><span className="micro muted">/ {pages}</span><button className="page-button" aria-label="Page suivante" disabled={page >= pages} onClick={() => update('page', String(page + 1))}><ChevronRight size={17} /></button></div></div>
    </div>}
    {!preview && <p className="availability-note">Les données de segmentation, d’encours, d’interactions et de scoring ne sont pas encore disponibles. Aucun score n’est calculé.</p>}
    {selected && <ClientDialog row={selected} close={() => setSelected(null)} />}
    {creating&&<CreateClient close={()=>setCreating(false)}/>}
  </>;
}
