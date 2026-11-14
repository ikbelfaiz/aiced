import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  CalendarPlus,
  Pencil,
  Plus,
  Phone,
  Sparkles,
} from "lucide-react";
import { Badge, Button, StatePanel } from "../../components/ui";
import { DataEditor, type Field } from "../../components/DataEditor";
import { workspaceApi, type Activity } from "../../lib/workspace-api";
import { useAuth } from "../auth/AuthProvider";

const date = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("fr-FR", {
        timeZone: "Africa/Tunis",
        hour12: false,
      })
    : "Non renseigné";
const kindLabels: Record<string, string> = {
  call: "Appel",
  email: "Email",
  meeting: "Rendez-vous",
  visit: "Visite",
};
const localInput = (value: string) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
function Pager({
  page,
  count,
  set,
}: {
  page: number;
  count: number;
  set: (page: number) => void;
}) {
  return (
    <div className="pagination">
      <span>{count} résultat(s)</span>
      <div>
        <Button disabled={page === 1} onClick={() => set(page - 1)}>
          Précédent
        </Button>
        <span>{page}</span>
        <Button disabled={page * 50 >= count} onClick={() => set(page + 1)}>
          Suivant
        </Button>
      </div>
    </div>
  );
}

export function ClientWorkspace() {
  const { id = "" } = useParams();
  return <ClientWorkspacePage key={id} id={id} />;
}

function ClientWorkspacePage({ id }: { id: string }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = params.get("onglet") ?? "overview";
  const [editor, setEditor] = useState<{
    section: string;
    item?: Activity;
    version?: number;
  } | null>(null);
  const [interactionPage, setInteractionPage] = useState(1),
    [opportunityPage, setOpportunityPage] = useState(1),
    [accountPage, setAccountPage] = useState(1);
  const detail = useQuery({
    queryKey: ["workspace", auth.identity?.session.id, id],
    queryFn: ({ signal }) => workspaceApi.get(id, signal),
  });
  const permissions = detail.data?.permissions;
  const interactions = useQuery({
    queryKey: ["interactions", auth.identity?.session.id, id, interactionPage],
    queryFn: ({ signal }) =>
      workspaceApi.activities(id, "interactions", interactionPage, signal),
    enabled: !!permissions?.view_interactions,
  });
  const opportunities = useQuery({
    queryKey: ["opportunities", auth.identity?.session.id, id, opportunityPage],
    queryFn: ({ signal }) =>
      workspaceApi.activities(id, "opportunities", opportunityPage, signal),
    enabled: !!permissions?.view_opportunities,
  });
  const accounts = useQuery({
    queryKey: [
      "workspace-accounts",
      auth.identity?.session.id,
      id,
      accountPage,
    ],
    queryFn: ({ signal }) => workspaceApi.accounts(id, accountPage, signal),
    enabled: !!permissions?.view_accounts,
  });
  const refresh = async () => {
    await Promise.all(
      [
        "workspace",
        "interactions",
        "opportunities",
        "workspace-accounts",
        "clients",
      ].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
    );
  };
  if (detail.isPending)
    return <StatePanel kind="loading" title="Chargement du client 360°…" />;
  if (detail.isError)
    return (
      <StatePanel
        kind="error"
        title="Fiche client inaccessible"
        retry={() => void detail.refetch()}
      >
        {detail.error.message}
      </StatePanel>
    );
  const client = detail.data;
  const activityList = (
    category: "interactions" | "opportunities",
    overview = false,
  ) => {
    const query = category === "interactions" ? interactions : opportunities;
    if (!client.permissions[`view_${category}`])
      return (
        <p className="unavailable-block">
          Habilitation spécifique requise pour consulter{" "}
          {category === "interactions"
            ? "les interactions"
            : "les opportunités"}
          .
        </p>
      );
    if (query.isPending)
      return <StatePanel kind="loading" title="Chargement de l’historique…" />;
    if (query.isError)
      return (
        <StatePanel
          kind="error"
          title="Historique inaccessible"
          retry={() => void query.refetch()}
        >
          {query.error.message}
        </StatePanel>
      );
    if (!query.data?.count)
      return (
        <StatePanel
          kind="empty"
          title={
            category === "interactions"
              ? "Aucune interaction enregistrée"
              : "Aucune opportunité enregistrée"
          }
        />
      );
    return (
      <>
        <div className="workspace-activities">
          {query.data.results.slice(0, overview ? 4 : 50).map((item) => (
            <article key={item.id}>
              <span className="activity-icon">
                <Phone size={17} />
              </span>
              <div>
                <div className="activity-title">
                  <strong>
                    {category === "interactions"
                      ? (kindLabels[item.kind!] ?? item.kind)
                      : item.title}
                  </strong>
                  <small>
                    {category === "interactions"
                      ? date(item.occurred_at)
                      : (item.due_date ?? "Sans échéance")}
                  </small>
                </div>
                {item.subject && <p>{item.subject}</p>}
                <p className="muted whitespace-pre-wrap">
                  {item.notes || "Aucune note"}
                </p>
                {category === "opportunities" && (
                  <p>
                    <Badge>
                      {
                        (
                          {
                            open: "Ouverte",
                            won: "Gagnée",
                            lost: "Perdue",
                          } as Record<string, string>
                        )[item.status!]
                      }
                    </Badge>{" "}
                    <strong>
                      {item.amount === null
                        ? "Montant non renseigné"
                        : `${item.amount} ${item.currency} · estimation commerciale AICED`}
                    </strong>
                  </p>
                )}
                <small className="muted">Source : AICED</small>
              </div>
              {client.permissions[`manage_${category}`] && (
                <button
                  className="icon-button"
                  aria-label={`Modifier ${item.subject ?? item.title}`}
                  onClick={() => setEditor({ section: category, item })}
                >
                  <Pencil size={15} />
                </button>
              )}
            </article>
          ))}
        </div>
        {!overview && (
          <Pager
            page={
              category === "interactions" ? interactionPage : opportunityPage
            }
            count={query.data.count}
            set={
              category === "interactions"
                ? setInteractionPage
                : setOpportunityPage
            }
          />
        )}
      </>
    );
  };
  const accountList = () =>
    !client.permissions.view_accounts ? (
      <p className="unavailable-block">
        Consultation financière non autorisée.
      </p>
    ) : accounts.isPending ? (
      <StatePanel kind="loading" title="Chargement des comptes…" />
    ) : accounts.isError ? (
      <StatePanel
        kind="error"
        title="Comptes inaccessibles"
        retry={() => void accounts.refetch()}
      >
        {accounts.error.message}
      </StatePanel>
    ) : !accounts.data?.count ? (
      <StatePanel kind="empty" title="Aucun compte source disponible" />
    ) : (
      <>
        <ul className="account-list">
          {accounts.data.results.map((account) => (
            <li key={account.id}>
              <strong>{account.product_label}</strong>
              <span>
                {account.external_id} · {account.source} · situation source :{" "}
                {date(account.source_as_of)}
              </span>
              <Badge>Lecture seule</Badge>
            </li>
          ))}
        </ul>
        <Pager
          page={accountPage}
          count={accounts.data.count}
          set={setAccountPage}
        />
      </>
    );
  let fields: Field[] = [],
    initial: Record<string, string> = {};
  if (editor?.section === "profile") {
    fields = [
      {
        name: "email",
        label: "Email commercial AICED",
        type: "email",
        maxLength: 254,
      },
      { name: "phone", label: "Téléphone commercial AICED", maxLength: 40 },
      {
        name: "profession",
        label: "Profession déclarée au CRM",
        maxLength: 120,
      },
      { name: "sector", label: "Secteur déclaré au CRM", maxLength: 120 },
      { name: "notes", label: "Notes CRM", type: "textarea" },
    ];
    initial = Object.fromEntries(
      fields.map((f) => [
        f.name,
        String(client.crm[f.name as keyof typeof client.crm] ?? ""),
      ]),
    );
  }
  if (editor?.section === "identity") {
    fields =
      client.kind === "physical"
        ? [
            {
              name: "first_name",
              label: "Prénom",
              required: true,
              maxLength: 100,
            },
            { name: "last_name", label: "Nom", required: true, maxLength: 100 },
          ]
        : [
            {
              name: "legal_name",
              label: "Raison sociale",
              required: true,
              maxLength: 200,
            },
          ];
    initial = client.identity;
  }
  if (editor?.section === "interactions") {
    fields = [
      {
        name: "kind",
        label: "Type d’interaction",
        options: Object.entries(kindLabels).map(([value, label]) => ({
          value,
          label,
        })),
      },
      { name: "subject", label: "Objet", required: true },
      {
        name: "occurred_at",
        label: "Date et heure de l’interaction réalisée",
        type: "datetime-local",
        required: true,
      },
      { name: "notes", label: "Compte rendu", type: "textarea" },
    ];
    initial = {
      kind: editor.item?.kind ?? "call",
      subject: editor.item?.subject ?? "",
      occurred_at: localInput(
        editor.item?.occurred_at ?? new Date().toISOString(),
      ),
      notes: editor.item?.notes ?? "",
    };
  }
  if (editor?.section === "opportunities") {
    fields = [
      { name: "title", label: "Intitulé", required: true },
      {
        name: "amount",
        label: "Estimation commerciale en TND (facultatif)",
        type: "number",
      },
      {
        name: "status",
        label: "État commercial",
        options: [
          { value: "open", label: "Ouverte" },
          { value: "won", label: "Gagnée" },
          { value: "lost", label: "Perdue" },
        ],
      },
      { name: "due_date", label: "Échéance", type: "date" },
      { name: "notes", label: "Notes commerciales", type: "textarea" },
    ];
    initial = {
      title: editor.item?.title ?? "",
      amount: editor.item?.amount ?? "",
      status: editor.item?.status ?? "open",
      due_date: editor.item?.due_date ?? "",
      notes: editor.item?.notes ?? "",
    };
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="page-eyebrow">Clients / Vue 360° · AICED</p>
          <h1>{client.display_name}</h1>
          <p className="page-subtitle">
            {client.is_prospect ? 'Fiche prospect AICED' : 'Fiche client 360°'} · {client.id.slice(0, 8)} · Créé le{" "}
            {new Date(client.created_at).toLocaleDateString("fr-TN")}
          </p>
        </div>
        <div className="heading-actions">
          <Button
            disabled={!client.permissions.edit_crm}
            onClick={() =>
              setEditor({ section: "profile", version: client.crm.version })
            }
          >
            <Pencil size={16} />
            Modifier le profil CRM
          </Button>
          <Button
            variant="primary"
            disabled={
              !client.permissions.manage_interactions ||
              !client.permissions.view_interactions
            }
            onClick={() => setEditor({ section: "interactions" })}
          >
            <CalendarPlus size={17} />
            Ajouter une interaction
          </Button>
        </div>
      </div>
      <div className="client-meta-row">
        <div>
          <Badge tone={client.origin === "AICED" ? "green" : "blue"}>
            Identité : {client.origin}
          </Badge>
          <Badge>CRM : AICED</Badge>
          <span>Carthago : non connecté</span>
        </div>
        <Link className="text-link" to={client.is_prospect ? '/prospects' : '/clients'}>
          <ArrowLeft size={12} /> {client.is_prospect ? 'Retour aux prospects' : 'Retour au panorama clients'}
        </Link>
      </div>
      <nav className="workspace-tabs" aria-label="Sections de la fiche client">
        {[
          ["overview", "Vue générale"],
          ["accounts", "Comptes"],
          ["investments", "Investissements"],
          ["interactions", "Interactions"],
          ["opportunities", "Opportunités"],
          ["documents", "Documents"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-current={tab === key ? "page" : undefined}
            className={tab === key ? "selected" : ""}
            onClick={() => setParams({ onglet: key })}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "overview" ? (
        <>
          <div className="client-overview-grid">
            <section className="card workspace-card">
              <h2>Profil client</h2>
              <div className="profile-data">
                <div>
                  <small>Profession · CRM AICED</small>
                  <p>{client.crm.profession || "Non renseignée"}</p>
                </div>
                <div>
                  <small>Secteur · CRM AICED</small>
                  <p>{client.crm.sector || "Non renseigné"}</p>
                </div>
                <div>
                  <small>Profil de risque source</small>
                  <p>Non disponible</p>
                </div>
                <div>
                  <small>Connaissance des marchés</small>
                  <p>Non disponible</p>
                </div>
              </div>
              <div className="profile-contact">
                <p>{client.crm.email || "Email CRM non renseigné"}</p>
                <p>{client.crm.phone || "Téléphone CRM non renseigné"}</p>
              </div>
              <p className="muted micro">
                Identité {client.origin} ·{" "}
                {client.permissions.edit_identity
                  ? "modifiable avec habilitation"
                  : "lecture seule"}
              </p>
              {client.permissions.edit_identity && (
                <Button
                  onClick={() =>
                    setEditor({ section: "identity", version: client.version })
                  }
                >
                  <Pencil size={14} />
                  Modifier l’identité AICED
                </Button>
              )}
            </section>
            <section className="card workspace-card investment-card">
              <h2>Portefeuille d’investissement</h2>
              <p className="card-subtitle">
                Source en lecture seule · aucune valorisation calculée
              </p>
              <div className="investment-unavailable">
                <strong>—</strong>
                <p>Encours et répartition non disponibles</p>
                <span>Aucune synchronisation Carthago active</span>
              </div>
              <p className="muted micro">
                Dernière situation source locale autorisée :{" "}
                {date(client.provenance.last_local_source_as_of)}
              </p>
              {accountList()}
              <p className="muted micro mt-5">
                Les comptes et attributs source ne peuvent pas être modifiés
                depuis AICED.
              </p>
            </section>
            <section className="card workspace-card">
              <h2>Relation commerciale</h2>
              <div className="profile-data">
                <div>
                  <small>Responsable</small>
                  <p>
                    {client.relationship_manager ||
                      "Non affecté"}
                  </p>
                </div>
                <div>
                  <small>Dernier contact autorisé</small>
                  <p>
                    {client.permissions.view_interactions
                      ? date(interactions.data?.results[0]?.occurred_at)
                      : "Accès restreint"}
                  </p>
                </div>
              </div>
              <div className="commercial-highlight">
                <small>OPPORTUNITÉS AICED</small>
                <p>
                  {client.permissions.view_opportunities
                    ? `${opportunities.data?.count ?? "—"} dossier(s) commercial(aux)`
                    : "Accès restreint"}
                </p>
                <p>Aucun score de potentiel calculé</p>
              </div>
              <button
                className="text-link mt-5"
                onClick={() => setParams({ onglet: "opportunities" })}
              >
                Consulter les opportunités →
              </button>
            </section>
          </div>
          <div className="client-overview-bottom">
            <section className="card workspace-card">
              <div className="card-title-row">
                <div>
                  <h2>Interactions récentes</h2>
                  <p className="card-subtitle">
                    Historique partagé selon vos habilitations
                  </p>
                </div>
                <button
                  className="text-link"
                  onClick={() => setParams({ onglet: "interactions" })}
                >
                  Tout l’historique
                </button>
              </div>
              {activityList("interactions", true)}
            </section>
            <section className="card workspace-card assistant-unavailable">
              <h2>Résumé intelligent du client</h2>
              <p className="card-subtitle">
                Assistant AICED · fonctionnalité non disponible
              </p>
              <p className="assistant-label">
                <Sparkles size={19} />
                Aide à la décision
              </p>
              <p>
                Aucun résumé automatique, risque de désengagement ou
                recommandation n’est calculé dans cette version.
              </p>
              <h3 className="mt-6 mb-3 font-semibold">
                Notes commerciales AICED
              </h3>
              <p className="whitespace-pre-wrap">
                {client.crm.notes || "Aucune note CRM enregistrée."}
              </p>
              <Button disabled className="mt-6">
                <Sparkles size={16} />
                Interroger l’assistant
              </Button>
            </section>
          </div>
        </>
      ) : tab === "accounts" ? (
        <section className="card workspace-card">
          <h2>Comptes source · lecture seule</h2>
          {accountList()}
        </section>
      ) : tab === "interactions" || tab === "opportunities" ? (
        <section className="card workspace-card">
          <div className="card-title-row">
            <h2>
              {tab === "interactions"
                ? "Historique des interactions"
                : "Opportunités commerciales"}
            </h2>
            <Button
              variant="primary"
              disabled={
                !client.permissions[`manage_${tab}`] ||
                !client.permissions[`view_${tab}`]
              }
              onClick={() => setEditor({ section: tab })}
            >
              <Plus size={16} />
              Ajouter{" "}
              {tab === "interactions" ? "une interaction" : "une opportunité"}
            </Button>
          </div>
          {activityList(tab)}
        </section>
      ) : (
        <section className="card">
          <StatePanel
            kind="empty"
            title={
              tab === "investments"
                ? "Données d’investissement non connectées"
                : "Documents non disponibles"
            }
          >
            Aucune donnée source ou fonctionnalité n’est simulée dans cette
            section.
          </StatePanel>
        </section>
      )}
      {editor && (
        <DataEditor
          title={
            editor.section === "profile"
              ? "Modifier le profil CRM"
              : editor.section === "identity"
                ? "Modifier l’identité AICED"
                : editor.section === "interactions"
                  ? editor.item
                    ? "Modifier une interaction"
                    : "Ajouter une interaction"
                  : editor.item
                    ? "Modifier une opportunité"
                    : "Ajouter une opportunité"
          }
          fields={fields}
          initial={initial}
          close={() => setEditor(null)}
          save={async (values) => {
            if (editor.section === "profile" || editor.section === "identity")
              await workspaceApi.edit(id, editor.section, {
                ...values,
                version: editor.version,
              });
            else {
              const payload: Record<string, unknown> = { ...values };
              if (editor.section === "interactions")
                payload.occurred_at = new Date(
                  values.occurred_at,
                ).toISOString();
              else {
                payload.amount = values.amount || null;
                payload.due_date = values.due_date || null;
                payload.currency = "TND";
              }
              if (editor.item) payload.version = editor.item.version;
              await workspaceApi.saveActivity(
                id,
                editor.section,
                payload,
                editor.item?.id,
              );
            }
            await refresh();
          }}
        />
      )}
    </>
  );
}
