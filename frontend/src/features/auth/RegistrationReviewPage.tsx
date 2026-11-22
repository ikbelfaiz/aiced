import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from './AuthProvider';
import { Button, StatePanel } from '../../components/ui';
import { mutate, request, type Page } from '../../lib/api';

type Item = { id: string; username: string; email: string; created_at: string };

function Requests({ organizationId }: { organizationId: string }) {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const key = ['registration-requests', organizationId];
  const query = useQuery({ queryKey: [...key, page], queryFn: ({ signal }) => request<Page<Item>>(`/api/organizations/${organizationId}/registrations/?page=${page}`, { signal }) });
  async function review(id: string, decision: 'approved' | 'rejected') {
    setBusy(true); setError(''); setMessage('');
    try {
      await mutate(`/api/organizations/${organizationId}/registrations/${id}/`, { decision });
      setMessage(decision === 'approved' ? 'Compte activé. Les habilitations métier doivent être attribuées séparément.' : 'Demande refusée. Le compte reste inactif.');
      setPage(1);
      await client.invalidateQueries({ queryKey: key });
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'La décision a échoué.'); }
    finally { setBusy(false); }
  }
  return <>
    {message && <p role="status">{message}</p>}{error && <p role="alert" className="form-error">{error}</p>}
    {query.isPending ? <StatePanel kind="loading" title="Chargement des demandes…" /> : query.isError ? <StatePanel kind="error" title="Chargement impossible" retry={() => void query.refetch()}>{query.error.message}</StatePanel> : <>
      {!query.data.results.length && <StatePanel kind="empty" title="Aucune demande en attente" />}
      <ul className="registration-list">{query.data.results.map(item => <li key={item.id}><div><strong>{item.username}</strong><p>{item.email}</p><span className="muted">Demandé le {new Date(item.created_at).toLocaleDateString('fr-FR')}</span></div><div className="registration-actions"><Button variant="primary" disabled={busy} onClick={() => void review(item.id, 'approved')}>Approuver</Button><Button disabled={busy} onClick={() => void review(item.id, 'rejected')}>Refuser</Button></div></li>)}</ul>
      <div className="registration-actions"><Button disabled={busy || page === 1} onClick={() => setPage(page - 1)}>Précédent</Button><span>Page {page}</span><Button disabled={busy || !query.data.next} onClick={() => setPage(page + 1)}>Suivant</Button></div>
    </>}
  </>;
}

export function RegistrationReviewPage() {
  const auth = useAuth();
  const [selected, setSelected] = useState('');
  const organizations = [...new Map((auth.identity?.access.assignments ?? []).filter(grant => grant.scope === 'organization' && grant.permissions.includes('users.manage') && (!grant.expires_at || new Date(grant.expires_at).getTime() > Date.now())).map(grant => [grant.organization_id, grant.organization_name])).entries()];
  const organizationId = organizations.some(([id]) => id === selected) ? selected : organizations[0]?.[0];
  if (!organizationId) return <StatePanel kind="denied" title="Accès non autorisé">La gestion des comptes nécessite une habilitation explicite dans votre institution.</StatePanel>;
  return <section className="registration-review"><h1>Demandes de compte</h1><p>Vérifiez l’identité du demandeur par votre canal interne avant d’approuver. L’email n’est pas vérifié automatiquement. L’approbation n’accorde aucun droit métier.</p><label htmlFor="registration-organization">Institution</label><select id="registration-organization" value={organizationId} onChange={event => setSelected(event.target.value)}>{organizations.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><Requests key={organizationId} organizationId={organizationId} /></section>;
}
