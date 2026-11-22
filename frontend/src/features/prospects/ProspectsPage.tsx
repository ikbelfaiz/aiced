import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, UserPlus, ChevronDown } from "lucide-react";
import { z } from "zod";
import { request, mutate } from "../../lib/api";
import { useAuth } from "../auth/AuthProvider";
import { Badge, Button, Dialog, StatePanel } from "../../components/ui";
import { DataEditor, type Field } from "../../components/DataEditor";

const prospect = z.object({
  id: z.string(),
  display_name: z.string(),
  kind: z.string(),
  source: z.string(),
  status: z.string(),
  next_action: z.string(),
  next_action_date: z.string().nullable(),
  version: z.number(),
  relationship_manager: z.string().nullable(),
  last_interaction: z.string().nullable().optional(),
  can_edit: z.boolean(),
});
const resultSchema = z.object({
  count: z.number(),
  results: z.array(prospect),
});
type Prospect = z.infer<typeof prospect>;
const statuses = [
  { value: "contact", label: "À contacter" },
  { value: "qualified", label: "Qualifié" },
  { value: "discussion", label: "En discussion" },
  { value: "follow_up", label: "À relancer" },
  { value: "closed", label: "Clos" },
];
const qualification: Field[] = [
  { name: "source", label: "Source du contact", maxLength: 120 },
  { name: "status", label: "Statut", options: statuses },
  { name: "next_action", label: "Prochaine action", maxLength: 160 },
  {
    name: "next_action_date",
    label: "Date de la prochaine action",
    type: "date",
  },
];
const displayDate = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleDateString("fr-FR", { timeZone: "Africa/Tunis" })
    : "—";

export function ProspectsPage() {
  const auth = useAuth();
  const cache = useQueryClient();
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Prospect | null>(null),
    [creating, setCreating] = useState(false);
  const allowed = auth.can("prospects.view") && auth.can("clients.view");
  const query = useQuery({
    queryKey: ["prospects", auth.identity?.session.id, search, status, page],
    queryFn: async ({ signal }) =>
      resultSchema.parse(
        await request(
          `/api/prospects/?${new URLSearchParams({ search, status, page: String(page), page_size: "8" })}`,
          { signal },
        ),
      ),
    enabled: allowed,
    retry: false,
  });
  const context = useQuery({
    queryKey: ["prospect-context", auth.identity?.session.id],
    queryFn: () =>
      request<{ organizations: { id: string; name: string }[] }>(
        "/api/prospects/context/",
      ),
    enabled: allowed && creating,
  });
  const refresh = () => cache.invalidateQueries({ queryKey: ["prospects"] });
  if (!allowed)
    return (
      <StatePanel kind="denied" title="Accès aux prospects non autorisé">
        Les habilitations clients et prospects sont requises.
      </StatePanel>
    );
  const count = query.data?.count;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="page-eyebrow">AICED · COMMERCIAL</p>
          <h1>Prospects</h1>
          <p className="page-subtitle">
            Qualifiez les nouveaux contacts et préparez les prochaines étapes de
            la relation.
          </p>
        </div>
        <Button
          variant="primary"
          disabled={
            !auth.can("prospects.manage") || !auth.can("clients.create")
          }
          onClick={() => setCreating(true)}
        >
          <UserPlus size={18} />
          Nouveau prospect
        </Button>
      </div>
      <section className="prospect-metrics" aria-label="Synthèse des prospects">
        <article className="card">
          <span>Prospects correspondants</span>
          <strong>{count ?? "—"}</strong>
          <small>Périmètre et filtres autorisés</small>
        </article>
        {[
          ["Qualification", "Statut manuel"],
          ["Prochaine action", "Planification AICED"],
          ["Conversion en clients", "Non calculée"],
        ].map(([label, value]) => (
          <article className="card" key={label}>
            <span>{label}</span>
            <strong className="unavailable-value">{value}</strong>
            <small>Aucune règle de score appliquée</small>
          </article>
        ))}
      </section>
      <section
        className="card filter-card prospect-filters"
        aria-label="Recherche et filtres prospects"
      >
        <div className="input-with-icon client-search">
          <Search size={18} />
          <input
            aria-label="Rechercher un prospect"
            placeholder="Rechercher un prospect, une entreprise…"
            value={search}
            maxLength={200}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="filter-row">
          <label className="select-wrap">
            <span className="sr-only">Statut du prospect</span>
            <select
              aria-label="Statut du prospect"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Tous les statuts</option>
              {statuses.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </label>
          <Button
            variant="text"
            onClick={() => {
              setSearch("");
              setStatus("");
              setPage(1);
            }}
          >
            Réinitialiser les filtres
          </Button>
        </div>
      </section>
      {query.isPending ? (
        <StatePanel kind="loading" title="Chargement des prospects…" />
      ) : query.isError ? (
        <StatePanel
          kind="error"
          title="Impossible de charger les prospects"
          retry={() => void query.refetch()}
        >
          {query.error.message}
        </StatePanel>
      ) : !query.data.results.length ? (
        <StatePanel kind="empty" title="Aucun prospect dans cette sélection">
          Créez un contact AICED ou modifiez les filtres.
        </StatePanel>
      ) : (
        <div className="client-table-card">
          <div
            className="table-scroll"
            tabIndex={0}
            aria-label="Tableau des prospects"
          >
            <table className="prospect-table">
              <thead>
                <tr>
                  {[
                    "Prospect",
                    "Source",
                    "Potentiel",
                    "Commercial affecté",
                    "Dernière interaction",
                    "Prochaine action",
                    "Statut",
                    "Actions",
                  ].map((label) => (
                    <th key={label} scope="col">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {query.data.results.map((row) => (
                  <tr key={row.id}>
                    <th scope="row">
                      <Link className="text-link" to={`/clients/${row.id}`}>
                        {row.display_name}
                      </Link>
                      <span className="client-reference" title={row.id}>
                        AICED ·{" "}
                        {row.kind === "legal"
                          ? "Entreprise"
                          : "Personne physique"}
                      </span>
                    </th>
                    <td>{row.source || "Non renseignée"}</td>
                    <td className="muted">Non calculé</td>
                    <td>{row.relationship_manager ?? "Non affecté"}</td>
                    <td>{displayDate(row.last_interaction)}</td>
                    <td>
                      {row.next_action || "Non renseignée"}
                      <span className="client-reference">
                        {displayDate(row.next_action_date)}
                      </span>
                    </td>
                    <td>
                      <Badge
                        tone={
                          row.status === "qualified"
                            ? "green"
                            : row.status === "follow_up"
                              ? "amber"
                              : "blue"
                        }
                      >
                        {statuses.find((s) => s.value === row.status)?.label ??
                          row.status}
                      </Badge>
                    </td>
                    <td>
                      {row.can_edit && (
                        <Button variant="text" onClick={() => setEditing(row)}>
                          Qualifier
                        </Button>
                      )}
                      <Link
                        className="text-link"
                        to={`/clients/${row.id}?onglet=opportunities`}
                      >
                        Opportunités
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>
              {(page - 1) * 8 + 1}–{Math.min(page * 8, query.data.count)} sur{" "}
              {query.data.count} prospects
            </span>
            <div>
              <Button disabled={page === 1} onClick={() => setPage(page - 1)}>
                Précédent
              </Button>
              <span>{page}</span>
              <Button
                disabled={page * 8 >= query.data.count}
                onClick={() => setPage(page + 1)}
              >
                Suivant
              </Button>
            </div>
          </div>
        </div>
      )}
      <p className="availability-note">
        Données commerciales AICED · Carthago non connecté. Aucun encours ni
        rapprochement automatique.
      </p>
      {editing && (
        <DataEditor
          title="Qualifier le prospect"
          fields={qualification}
          initial={{
            source: editing.source,
            status: editing.status,
            next_action: editing.next_action,
            next_action_date: editing.next_action_date ?? "",
          }}
          close={() => setEditing(null)}
          save={async (values) => {
            await mutate(
              `/api/prospects/${editing.id}/`,
              {
                ...values,
                next_action_date: values.next_action_date || null,
                version: editing.version,
              },
              "PATCH",
            );
            await refresh();
          }}
        />
      )}
      {creating &&
      (context.isPending ||
        context.isError ||
        !context.data?.organizations.length) ? (
        <Dialog title="Nouveau prospect" onClose={() => setCreating(false)}>
          <StatePanel
            kind={
              context.isPending
                ? "loading"
                : context.isError
                  ? "error"
                  : "denied"
            }
            title={
              context.isPending
                ? "Chargement des organisations…"
                : "Aucune organisation disponible"
            }
            retry={context.isError ? () => void context.refetch() : undefined}
          />
        </Dialog>
      ) : (
        creating &&
        context.data && (
          <DataEditor
            title="Nouveau prospect"
            description="Contact local AICED, sans modification ni rapprochement Carthago. Données synthétiques uniquement en développement."
            fields={[
              {
                name: "organization_id",
                label: "Organisation",
                options: context.data.organizations.map((org) => ({
                  value: org.id,
                  label: org.name,
                })),
              },
              {
                name: "kind",
                label: "Type de personne",
                options: [
                  { value: "physical", label: "Personne physique" },
                  { value: "legal", label: "Personne morale" },
                ],
              },
              {
                name: "first_name",
                label: "Prénom (personne physique)",
                maxLength: 100,
              },
              {
                name: "last_name",
                label: "Nom (personne physique)",
                maxLength: 100,
              },
              {
                name: "legal_name",
                label: "Raison sociale (personne morale)",
                maxLength: 200,
              },
              ...qualification,
            ]}
            close={() => setCreating(false)}
            save={async (values) => {
              const identity =
                values.kind === "physical"
                  ? {
                      first_name: values.first_name,
                      last_name: values.last_name,
                    }
                  : { legal_name: values.legal_name };
              await mutate("/api/prospects/", {
                organization_id: values.organization_id,
                kind: values.kind,
                ...identity,
                qualification: {
                  source: values.source,
                  status: values.status,
                  next_action: values.next_action,
                  next_action_date: values.next_action_date || null,
                },
              });
              setPage(1);
              setSearch("");
              setStatus("");
              await refresh();
            }}
          />
        )
      )}
    </>
  );
}
