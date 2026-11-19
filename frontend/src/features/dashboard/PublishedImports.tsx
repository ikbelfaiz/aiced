import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button, StatePanel } from '../../components/ui';
import { importApi, type ImportOrganization } from '../../lib/workspace-api';
import { useAuth } from '../auth/AuthProvider';

const labels: Record<string, string> = {
  physical: 'Personnes physiques', legal: 'Personnes morales', accounts: 'Comptes titres',
};

export function PublishedImports() {
  const auth = useAuth();
  const permitted = auth.can('imports.view') && auth.can('clients.view_financial');
  const context = useQuery({ queryKey: ['dashboard-import-context', auth.identity?.session.id],
    queryFn: importApi.context, enabled: permitted, retry: false, refetchOnWindowFocus: false });
  if (!permitted) return null;
  if (context.isPending) return <StatePanel kind="loading" title="Chargement des imports publiés…" />;
  if (context.isError) return <StatePanel kind="error" title="Imports publiés inaccessibles" retry={() => void context.refetch()} />;
  if (!context.data.organizations.length) return null;
  return <PublishedWorkspace organizations={context.data.organizations} session={auth.identity?.session.id ?? ''} />;
}

function PublishedWorkspace({ organizations, session }: { organizations: ImportOrganization[]; session: string }) {
  const [organizationId, setOrganizationId] = useState(organizations[0].id);
  const organization = organizations.find(item => item.id === organizationId) ?? organizations[0];
  const [batchPage, setBatchPage] = useState(1);
  const [batchId, setBatchId] = useState('');
  const [rowPage, setRowPage] = useState(1);
  const batches = useQuery({ queryKey: ['dashboard-published-batches', session, organization.id, batchPage],
    queryFn: () => importApi.batches(organization.id, batchPage), retry: false, refetchOnWindowFocus: false });
  const rows = useQuery({ queryKey: ['dashboard-published-rows', session, organization.id, batchId, rowPage],
    queryFn: () => importApi.preview(organization.id, batchId, rowPage), enabled: !!batchId,
    retry: false, refetchOnWindowFocus: false });
  const published = !batches.isError ? batches.data?.results.filter(item => item.status === 'published') ?? [] : [];
  const selected = published.find(item => item.id === batchId);
  const detail = selected && !rows.isError && rows.data?.batch.status === 'published' && rows.data.batch.id === selected.id ? rows.data : undefined;
  const accepted = detail?.results.filter(row => row.errors.length === 0) ?? [];
  return <section className="card workspace-card" aria-label="Données importées publiées">
    <h2>Données importées publiées</h2>
    <p>Source Excel en lecture seule, après revue indépendante. Les lignes rejetées sont exclues. Les personnes et sociétés synthétiques peuvent être liées à des clients de test.</p>
    <label className="organization-select">Organisation
      <select value={organization.id} onChange={event => { setOrganizationId(event.target.value); setBatchPage(1); setBatchId(''); setRowPage(1); }}>
        {organizations.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    {batches.isPending ? <StatePanel kind="loading" title="Chargement des lots…" /> : batches.isError ?
      <StatePanel kind="error" title="Lots inaccessibles" retry={() => void batches.refetch()} /> : <>
        {published.length ? <ul>{published.map(item => <li key={item.id}>
          <button type="button" className="text-link" onClick={() => { setBatchId(item.id); setRowPage(1); }}>
            {labels[item.template] ?? item.template} · situation {item.source_as_of} · {item.published_rows} ligne(s) publiée(s) · {item.data_scope === 'synthetic' ? 'synthétique' : item.data_scope === 'operational' ? 'opérationnel' : 'historique non classifié'}
          </button>
        </li>)}</ul> : <p>Aucun lot publié sur cette page.</p>}
        <div className="pagination"><Button disabled={batchPage === 1} onClick={() => { setBatchPage(batchPage - 1); setBatchId(''); }}>Précédent</Button><span>Lots · page {batchPage}</span><Button disabled={!batches.data?.next} onClick={() => { setBatchPage(batchPage + 1); setBatchId(''); }}>Suivant</Button></div>
      </>}
    {selected && <div>
      <h3>{labels[selected.template] ?? selected.template} · situation {selected.source_as_of}</h3>
      <p>Publié le {selected.published_at ? new Date(selected.published_at).toLocaleString('fr-FR', { timeZone: 'Africa/Tunis' }) : '—'} · lot {selected.id}</p>
      {rows.isPending ? <StatePanel kind="loading" title="Chargement des lignes…" /> : rows.isError ?
        <StatePanel kind="error" title="Lignes inaccessibles" retry={() => void rows.refetch()} /> : detail && <>
          {accepted.length ? <div className="table-scroll staging-scroll" tabIndex={0} aria-label="Lignes publiées, défilement horizontal">
            <table className="staging-table"><thead><tr><th>Ligne</th>{detail.headers.map((header, index) => <th key={index}>{index + 1} · {header ?? 'Sans libellé'}</th>)}</tr></thead>
              <tbody>{accepted.map(row => <tr key={row.id}><th>{row.number}</th>{detail.headers.map((_, index) => <td key={index}>{String(row.cells[String(index + 1)] ?? '—')}</td>)}</tr>)}</tbody></table>
          </div> : <p>Aucune ligne publiée sur cette page.</p>}
          <div className="pagination"><Button disabled={rowPage === 1} onClick={() => setRowPage(rowPage - 1)}>Précédent</Button><span>Lignes · page {rowPage}</span><Button disabled={!detail.next} onClick={() => setRowPage(rowPage + 1)}>Suivant</Button></div>
        </>}
    </div>}
  </section>;
}
