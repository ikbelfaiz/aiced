import { useQuery } from '@tanstack/react-query';
import { request } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';

type Field = { label: string; value: unknown };
type Source = { source_id: string; source_as_of: string; batch_id: string; fields: Field[]; accounts: {source_id: string; source_as_of: string; fields: Field[]}[]; accounts_more: boolean };

export function SyntheticImport({ id, allowed }: { id: string; allowed: boolean }) {
  const auth = useAuth();
  const query = useQuery({
    queryKey: ['synthetic-import', auth.identity?.session.id, id],
    queryFn: ({ signal }) => request<{ source: Source | null }>(`/api/clients/${encodeURIComponent(id)}/synthetic-import/`, { signal }),
    enabled: allowed && auth.can('imports.view'), retry: false,
  });
  if (!allowed || !auth.can('imports.view') || (!query.data?.source && !query.isError)) return null;
  if (query.isError) return <p className="availability-note">Données source synthétiques indisponibles.</p>;
  const source = query.data!.source!;
  return <section className="card workspace-card"><h2>Import synthétique · lecture seule</h2>
    <p className="availability-note">Données de test · identifiant source {source.source_id} · situation {source.source_as_of} · lot {source.batch_id}</p>
    <dl>{source.fields.map((field, index) => <div key={index}><dt>{field.label}</dt><dd>{String(field.value)}</dd></div>)}</dl>
    <h3>Comptes synthétiques liés</h3>
    {source.accounts.length === 0 ? <p>Aucun compte synthétique lié.</p> : source.accounts.map(account => <details key={account.source_id}><summary>TEST · Compte {account.source_id} · situation {account.source_as_of}</summary><dl>{account.fields.map((field, index) => <div key={index}><dt>{field.label}</dt><dd>{String(field.value)}</dd></div>)}</dl></details>)}
    {source.accounts_more && <p>Seuls les 50 premiers comptes sont affichés.</p>}
  </section>;
}
