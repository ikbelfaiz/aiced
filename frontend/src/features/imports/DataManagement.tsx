import { useState, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, ShieldCheck, Database, Plus, Download } from "lucide-react";
import { Badge, Button, Dialog, StatePanel } from "../../components/ui";
import { DataEditor } from "../../components/DataEditor";
import {
  importApi,
  type Batch,
  type ImportOrganization,
  type Template,
} from "../../lib/workspace-api";
import { useAuth } from "../auth/AuthProvider";

const templateLabels: Record<string, string> = {
  physical: "Tiers personnes physiques",
  legal: "Tiers personnes morales",
  accounts: "Comptes titres",
};
const today = () => new Date().toLocaleDateString("en-CA");
const formatDate = (value: string) =>
  new Date(value).toLocaleString("fr-FR", {
    timeZone: "Africa/Tunis",
    hour12: false,
  });

export function DataManagement() {
  const auth = useAuth();
  const context = useQuery({
    queryKey: ["import-context", auth.identity?.session.id],
    queryFn: importApi.context,
    enabled: auth.can("imports.view") && auth.can("clients.view_financial"),
  });
  const [selection, setSelection] = useState("");
  const org =
    context.data?.organizations.find((item) => item.id === selection) ??
    context.data?.organizations[0];
  if (!auth.can("imports.view") || !auth.can("clients.view_financial"))
    return (
      <StatePanel kind="denied" title="Gestion des données non autorisée">
        Une habilitation d’import et financière à l’échelle de l’organisation
        est requise.
      </StatePanel>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="page-eyebrow">ADMINISTRATION · AICED</p>
          <h1>Gestion des données</h1>
          <p className="page-subtitle">
            Contrôler les fichiers, examiner les rejets et publier des snapshots
            source traçables.
          </p>
        </div>
        <Badge tone="blue">
          <Database size={14} />
          Carthago · lecture seule
        </Badge>
      </div>
      {context.isPending ? (
        <StatePanel
          kind="loading"
          title="Chargement des habilitations d’import…"
        />
      ) : context.isError ? (
        <StatePanel
          kind="error"
          title="Gestion des données inaccessible"
          retry={() => void context.refetch()}
        >
          {context.error.message}
        </StatePanel>
      ) : !org ? (
        <StatePanel kind="denied" title="Aucune organisation autorisée">
          Les droits requis doivent porter sur la même organisation.
        </StatePanel>
      ) : (
        <>
          <label className="organization-select">
            Organisation autorisée
            <select
              value={org.id}
              onChange={(e) => setSelection(e.target.value)}
            >
              {context.data.organizations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <ImportWorkspace
            key={org.id}
            org={org}
            templates={context.data.templates}
          />
        </>
      )}
    </>
  );
}

function ImportWorkspace({
  org,
  templates,
}: {
  org: ImportOrganization;
  templates: Record<string, Template>;
}) {
  const auth = useAuth(),
    cache = useQueryClient();
  const reviewPanel = useRef<HTMLElement>(null);
  const [reviewSelection, setReviewSelection] = useState(0);
  useEffect(() => {
    if (reviewSelection) {
      reviewPanel.current?.scrollIntoView({ block: "start" });
      reviewPanel.current?.focus({ preventScroll: true });
    }
  }, [reviewSelection]);
  const [dataScope, setDataScope] = useState("");
  const [policyView, setPolicyView] = useState("approved");
  const [policyPage, setPolicyPage] = useState(1);
  const [tab, setTab] = useState("imports"),
    [template, setTemplate] = useState("legal"),
    [sourceDate, setSourceDate] = useState(today()),
    [snapshot, setSnapshot] = useState("partial"),
    [dateFormat, setDateFormat] = useState("ISO");
  const [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [batch, setBatch] = useState<Batch | null>(null),
    [page, setPage] = useState(1),
    [batchPage, setBatchPage] = useState(1),
    [rejected, setRejected] = useState(false),
    [policyForm, setPolicyForm] = useState(false);
  const [confirm, setConfirm] = useState(false),
    [policyId, setPolicyId] = useState(""),
    [exclude, setExclude] = useState(false);
  const [policyAction, setPolicyAction] = useState<{
    id: string;
    revoke: boolean;
  } | null>(null);
  const batches = useQuery({
    queryKey: ["import-batches", auth.identity?.session.id, org.id, batchPage],
    queryFn: () => importApi.batches(org.id, batchPage),
  });
  const policies = useQuery({
    queryKey: ["import-policies", auth.identity?.session.id, org.id, policyView, policyPage],
    queryFn: () => importApi.policies(org.id, policyView, policyPage),
  });
  const preview = useQuery({
    queryKey: [
      "import-preview",
      auth.identity?.session.id,
      org.id,
      batch?.id,
      page,
      rejected,
    ],
    queryFn: () => importApi.preview(org.id, batch!.id, page, rejected),
    enabled: !!batch,
  });
  const selected = preview.data?.batch ?? batch;
  const match = preview.data?.policy_match;
  const activePolicies = selected?.data_scope !== 'legacy' ? (match?.policy ? [match.policy] : []) : match?.legacy_policies ?? [];
  const effectivePolicyId = policyId || (match?.status === 'matched' ? match.policy?.id ?? '' : '');
  const publicationBlocks = selected?.status === 'staged' ? [
    ...(!org.approve ? ['Votre habilitation ne permet pas la publication. Un réviseur autorisé doit intervenir.'] : []),
    ...(selected.uploaded_by_id === auth.identity?.session.id ? ['Le déposant ne peut pas publier son propre lot : une revue par un autre utilisateur habilité est obligatoire.'] : []),
    ...(preview.isPending || preview.isFetching ? ['Chargement et validation des exigences de publication...'] : preview.isError ? ['Examen inaccessible : publication bloquée. Rechargez les détails.'] : []),
    ...(selected.data_scope === 'legacy' && !preview.isPending && activePolicies.length === 0 ? ['Aucune règle historique compatible. Une approbation indépendante est requise.'] : []),
    ...(selected.total === selected.rejected ? ['Aucune ligne valide : corrigez le fichier puis déposez un nouveau lot. Le staging existant reste conservé.'] : []),
    ...(selected.data_scope !== 'legacy' && match?.status !== 'matched' ? [match?.reason ?? 'Validation de la règle compatible en cours…'] : []),
  ] : [];
  const refresh = async () => {
    await Promise.all(
      ["import-batches", "import-preview", "import-policies"].map((key) =>
        cache.invalidateQueries({ queryKey: [key] }),
      ),
    );
  };
  const perform = async (operation: () => Promise<unknown>) => {
    setError("");
    setBusy(true);
    try {
      await operation();
      await refresh();
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Opération impossible.",
      );
    } finally {
      setBusy(false);
    }
  };
  const choose = (item: Batch) => {
    setBatch(item);
    setReviewSelection(value => value + 1);
    setPage(1);
    setRejected(false);
    setPolicyId("");
    setExclude(false);
    setError("");
  };
  return (
    <>
      <div className="source-rule-notice">
        <ShieldCheck size={20} />
        <div>
          <strong>
            Publication contrôlée · snapshots immuables uniquement
          </strong>
          <p>
            Aucun fichier ne modifie un client ou un compte Carthago. Aucune
            fusion par nom. Le rapprochement métier reste bloqué sans règle
            approuvée.
          </p>
        </div>
      </div>
      <nav className="workspace-tabs" aria-label="Gestion des données">
        {[
          ["imports", "Imports & historique"],
          ["policies", "Règles de publication"],
          ["templates", "Modèles Excel"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "selected" : ""}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && (
        <p className="form-error mb-5" role="alert">
          {error}
        </p>
      )}
      {tab === "imports" ? (
        <>
          {org.upload && (
            <section className="card workspace-card">
              <h2>Déposer un fichier Excel</h2>
              <p className="card-subtitle">
                XLSX uniquement · 10 Mio compressés / 25 Mio décompressés · 50
                000 lignes maximum · aucun contenu exécuté
              </p>
              <form
                className="import-upload-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!file) return;
                  void perform(async () => {
                    if (file.size > 10 * 1024 * 1024)
                      throw new Error("Fichier supérieur à 10 Mio.");
                    const result = await importApi.upload(
                      org.id,
                      file,
                      template,
                      sourceDate,
                      snapshot,
                      dateFormat,
                      dataScope,
                    );
                    choose(result);
                  });
                }}
              >
                <label>
                  Modèle versionné
                  <select
                    value={template}
                    onChange={(e) => setTemplate(e.target.value)}
                  >
                    {Object.keys(templates).map((key) => (
                      <option key={key} value={key}>
                        {templateLabels[key]} · v{templates[key].version}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Date de situation source
                  <input
                    aria-label="Date de situation source"
                    type="date"
                    required
                    max={today()}
                    value={sourceDate}
                    onChange={(e) => setSourceDate(e.target.value)}
                  />
                </label>
                <label>
                  Nature de l’export
                  <select
                    value={snapshot}
                    onChange={(e) => setSnapshot(e.target.value)}
                  >
                    <option value="partial">Partiel</option>
                    <option value="complete">
                      Complet déclaré (sans suppression)
                    </option>
                  </select>
                </label>
                <label>
                  Format des dates source
                  <select
                    aria-label="Format des dates source"
                    value={dateFormat}
                    onChange={(event) => setDateFormat(event.target.value)}
                  >
                    <option value="ISO">ISO · année-mois-jour</option>
                    <option value="DMY">
                      Jour/mois/année · choix explicite
                    </option>
                  </select>
                </label>
                <label>
                  Usage déclaré du fichier
                  <select aria-label="Usage déclaré du fichier" required value={dataScope} onChange={e => setDataScope(e.target.value)}>
                    <option value="">Choisir explicitement</option>
                    <option value="synthetic">Données synthétiques de test</option>
                    <option value="operational">Données opérationnelles · politique approuvée requise</option>
                  </select>
                </label>
                <label className="file-field">
                  Fichier XLSX
                  <input
                    aria-label="Fichier XLSX"
                    className="sr-only"
                    type="file"
                    accept=".xlsx"
                    required
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                  <span className="file-picker"><span>Choisir un fichier</span><span>{file?.name??'Aucun fichier choisi'}</span></span>
                </label>
                <Button variant="primary" disabled={busy || !file}>
                  <Upload size={16} />
                  {busy ? "Validation…" : "Valider et prévisualiser"}
                </Button>
              </form>
            </section>
          )}
          <section className="card workspace-card mt-6">
            <div className="card-title-row">
              <h2>Historique des imports</h2>
              <Button onClick={() => void refresh()} disabled={busy}>
                Actualiser
              </Button>
            </div>
            {batches.isPending ? (
              <StatePanel kind="loading" title="Chargement des lots…" />
            ) : batches.isError ? (
              <StatePanel
                kind="error"
                title="Lots inaccessibles"
                retry={() => void batches.refetch()}
              >
                {batches.error.message}
              </StatePanel>
            ) : !batches.data.count ? (
              <StatePanel kind="empty" title="Aucun import enregistré">
                Déposez un fichier synthétique conforme au modèle pour
                commencer.
              </StatePanel>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="imports-table">
                    <thead>
                      <tr>
                        <th>Modèle / date source</th>
                        <th>Déposé le</th>
                        <th>Lignes</th>
                        <th>Rejets</th>
                        <th>État</th>
                        <th>Revue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batches.data.results.map((item) => (
                        <tr key={item.id}>
                          <th>
                            {templateLabels[item.template]}
                            <span className="client-reference">
                              {item.source_as_of} ·{" "}
                              {item.snapshot_kind === "partial"
                                ? "partiel"
                                : "complet déclaré"}
                            </span>
                          </th>
                          <td>{formatDate(item.created_at)}</td>
                          <td>{item.total}</td>
                          <td>{item.rejected}</td>
                          <td>
                            <Badge
                              tone={
                                item.status === "published" ? "green" : "amber"
                              }
                            >
                              {item.status === "published"
                                ? "Snapshot publié"
                                : "En attente de revue"}
                            </Badge>
                          </td>
                          <td>
                            <button
                              className="text-link"
                              onClick={() => choose(item)}
                              aria-label={`Examiner le lot ${item.id}`}
                            >
                              Examiner →
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="pagination">
                  <span>{batches.data.count} lot(s)</span>
                  <div>
                    <Button
                      disabled={batchPage === 1}
                      onClick={() => setBatchPage(batchPage - 1)}
                    >
                      Précédent
                    </Button>
                    <span>{batchPage}</span>
                    <Button
                      disabled={!batches.data.next}
                      onClick={() => setBatchPage(batchPage + 1)}
                    >
                      Suivant
                    </Button>
                  </div>
                </div>
              </>
            )}
          </section>
          {selected && (
            <section ref={reviewPanel} tabIndex={-1} aria-label="Examen de l’import" style={{scrollMarginTop: 24}} className="card workspace-card mt-6">
              <div className="card-title-row">
                <div>
                  <h2>Prévisualisation du lot</h2>
                  <p className="card-subtitle">
                    {selected.id} · {templateLabels[selected.template]} · source
                    manuelle Excel
                  </p>
                </div>
                <Badge
                  tone={selected.status === "published" ? "green" : "amber"}
                >
                  {selected.status === "published"
                    ? "Snapshot publié · aucun client fusionné"
                    : "Staging · aucun effet métier"}
                </Badge>
              </div>
              {preview.isFetching && <p role="status">Chargement des détails et des exigences...</p>}
              <p>Import : {templateLabels[selected.template]} / {selected.source_as_of}</p>
              <p className="digest">
                Usage : {selected.data_scope === 'synthetic' ? 'Synthétique' : selected.data_scope === 'operational' ? 'Opérationnel' : 'Historique non classifié'} · Schéma v{selected.template_version} ·{' '}
                SHA-256 : {selected.digest} · Format des dates :{" "}
                {selected.date_format}
              </p>
              {match && selected.status === 'staged' && <p role="status">{match.reason}{match.policy && <> Règle suggérée : {match.policy.id}. Réutilisable pour les prochains fichiers compatibles.</>}</p>}
              {match?.configuration && <p>Règle approuvée identifiée : {match.configuration.id}. Le fichier ne satisfait pas sa colonne clé.</p>}
              <div className="batch-summary">
                <Badge>{selected.total} lignes</Badge>
                <Badge tone="red">{selected.rejected} rejet(s)</Badge>
                <Badge tone="green">
                  {selected.published_rows} snapshot(s) publié(s)
                </Badge>
                <span>Carthago : non connecté</span>
              </div>
              <section className="source-rule-notice" aria-label="État de publication">
                <div><strong>{selected.status === 'published' ? 'Publication enregistrée' : !preview.isFetching && !preview.isPending && publicationBlocks.length > 0 ? 'Publication bloquée' : 'En staging : données conservées, en attente de revue'}</strong>
                  {selected.status === 'published' ? <p>Publié le {selected.published_at ? formatDate(selected.published_at) : '—'} · réviseur : {selected.published_by_id} · règle : {selected.policy_id}. {selected.published_rows} snapshot(s) conservé(s), sans création de client ni de compte.</p> : <><p>La validation technique ne vaut pas approbation métier. Le dépôt n’est jamais publié automatiquement.</p>{publicationBlocks.length > 0 ? <ul>{publicationBlocks.map(reason=><li key={reason}>{reason}</li>)}</ul> : <p>Une règle compatible est disponible. Un réviseur autorisé peut examiner puis confirmer explicitement la publication.</p>}</>}
                </div>
              </section>
              <div className="preview-actions">
                <label>
                  <input
                    type="checkbox"
                    checked={rejected}
                    onChange={(e) => {
                      setRejected(e.target.checked);
                      setPage(1);
                    }}
                  />{" "}
                  Afficher uniquement les rejets
                </label>
                <a
                  className="button"
                  href={importApi.rejectionUrl(org.id, selected.id)}
                  download
                >
                  <Download size={15} />
                  Rapport des rejets CSV
                </a>
                <Button
                  variant="primary"
                  disabled={
                    !org.approve ||
                    selected.uploaded_by_id === auth.identity?.session.id ||
                    selected.status === "published" ||
                    busy ||
                    preview.isFetching ||
                    preview.isError
                    || publicationBlocks.length > 0
                  }
                  onClick={() => setConfirm(true)}
                >
                  Examiner la publication
                </Button>
              </div>
              {selected.uploaded_by_id === auth.identity?.session.id && (
                <p className="availability-note">
                  Le déposant ne peut pas publier son propre lot. Un autre
                  utilisateur habilité doit effectuer la revue.
                </p>
              )}
              {preview.isPending ? (
                <StatePanel kind="loading" title="Chargement des lignes…" />
              ) : preview.isError ? (
                <StatePanel
                  kind="error"
                  title="Prévisualisation inaccessible"
                  retry={() => void preview.refetch()}
                >
                  {preview.error.message}
                </StatePanel>
              ) : (
                preview.data && (
                  <>
                    <div
                      className="table-scroll staging-scroll"
                      tabIndex={0}
                      aria-label="Lignes importées, défilement horizontal"
                    >
                      <table className="staging-table">
                        <thead>
                          <tr>
                            <th>Ligne / validation</th>
                            {preview.data.headers.map((label, i) => (
                              <th key={i}>
                                {i + 1} · {label ?? "Sans libellé"}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.data.results.map((row) => (
                            <tr key={row.id}>
                              <th>
                                {row.number}
                                <Badge
                                  tone={row.errors.length ? "red" : "green"}
                                >
                                  {row.errors.length
                                    ? "Rejetée"
                                    : "Validée fichier"}
                                </Badge>
                                {row.errors.map((message, i) => (
                                  <p className="row-error" key={i}>
                                    {message}
                                  </p>
                                ))}
                                {row.warnings.map((message, i) => (
                                  <p className="row-warning" key={i}>
                                    {message}
                                  </p>
                                ))}
                              </th>
                              {preview.data.headers.map((_, i) => (
                                <td key={i}>
                                  {String(row.cells[String(i + 1)] ?? "—")}
                                  {row.normalized_dates[String(i + 1)] && (
                                    <span className="client-reference">
                                      Date normalisée :{" "}
                                      {row.normalized_dates[String(i + 1)]}
                                    </span>
                                  )}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="pagination">
                      <span>
                        {preview.data.count} ligne(s) · page {page}
                      </span>
                      <div>
                        <Button
                          disabled={page === 1}
                          onClick={() => setPage(page - 1)}
                        >
                          Précédent
                        </Button>
                        <Button
                          disabled={!preview.data.next}
                          onClick={() => setPage(page + 1)}
                        >
                          Suivant
                        </Button>
                      </div>
                    </div>
                  </>
                )
              )}
              <h3 className="mt-6 mb-3 font-semibold">Traçabilité du lot</h3>
              {(preview.data?.history ?? []).map((event, i) => (
                <p className="history-entry" key={i}>
                  {formatDate(event.timestamp)} · {event.action}
                </p>
              ))}
            </section>
          )}
        </>
      ) : tab === "policies" ? (
        <section className="card workspace-card">
          <div className="card-title-row">
            <div>
              <h2>Règles de publication réutilisables</h2>
              <p className="card-subtitle">
                Réutilisez une règle approuvée pour les fichiers compatibles. Une nouvelle version n’est nécessaire que si la configuration ou la politique change. Chaque lot reste soumis à une revue indépendante.
              </p>
            </div>
            {org.policy_manage && (
              <Button variant="primary" onClick={() => setPolicyForm(true)}>
                <Plus size={16} />
                Proposer une règle
              </Button>
            )}
          </div>
          <label className="organization-select mt-5">
            Modèle pour la nouvelle règle
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            >
              {Object.keys(templates).map((key) => (
                <option key={key} value={key}>
                  {templateLabels[key]}
                </option>
              ))}
            </select>
          </label>
          <p className="availability-note">Personnes physiques et comptes titres : les configurations opérationnelles manquantes doivent être approuvées par AMEN INVEST. Les colonnes candidates ne constituent pas une identité confirmée. Aucun modèle n’est activé automatiquement.</p>
          <label className="organization-select mt-5">Afficher les règles
            <select aria-label="Afficher les règles" value={policyView} onChange={e => {setPolicyView(e.target.value);setPolicyPage(1);}}>
              <option value="operational">Opérationnel : règles approuvées</option>
              <option value="synthetic">Tests synthétiques : règles approuvées</option>
              <option value="approved">Règles approuvées réutilisables</option>
              <option value="pending">Propositions en attente d’approbation</option>
              <option value="history">Historique révoqué et règles non classifiées</option>
            </select>
          </label>
          <p className="availability-note">Les anciennes règles ne sont ni supprimées, ni approuvées, ni reclassifiées automatiquement. Une règle synthétique ne peut pas publier un lot opérationnel. Révoquez explicitement la règle active avant d’approuver son remplacement.</p>
          {policies.isPending ? (
            <StatePanel kind="loading" title="Chargement des règles…" />
          ) : policies.isError ? (
            <StatePanel
              kind="error"
              title="Règles inaccessibles"
              retry={() => void policies.refetch()}
            >
              {policies.error.message}
            </StatePanel>
          ) : !policies.data.length ? (
            <StatePanel kind="empty" title="Aucune règle approuvée">
              La publication demeure bloquée jusqu’à une approbation
              indépendante.
            </StatePanel>
          ) : (
            <div className="policy-list">
              {policies.data.map((policy) => (
                <article key={policy.id}>
                  <div>
                    <strong>
                      {templateLabels[policy.template]} · colonne clé{" "}
                      {policy.key_column} · dates {policy.date_format}
                      {' · schéma v'}{policy.template_version}{' · '}{policy.data_scope === 'synthetic' ? 'Synthétique' : policy.data_scope === 'operational' ? 'Opérationnel' : 'Historique non classifié'}
                    </strong>
                    <Badge
                      tone={
                        policy.revoked_at
                          ? "red"
                          : policy.approved_at
                            ? "green"
                            : "amber"
                      }
                    >
                      {policy.revoked_at
                        ? "Révoquée"
                        : policy.approved_at
                          ? "Approuvée"
                          : "En attente"}
                    </Badge>
                  </div>
                  <p>{policy.rationale}</p>
                  <small>{policy.id} · snapshot immuable uniquement</small>
                  <p className="muted micro">
                    Créateur : {policy.created_by_id} · approbation :{" "}
                    {policy.approved_at
                      ? formatDate(policy.approved_at)
                      : "en attente"}
                  </p>
                  {org.approve && !policy.revoked_at && (
                    <div className="mt-3 flex gap-3">
                      {!policy.approved_at && (
                        <Button
                          disabled={
                            policy.created_by_id ===
                              auth.identity?.session.id || busy
                          }
                          onClick={() =>
                            setPolicyAction({ id: policy.id, revoke: false })
                          }
                        >
                          Approuver la règle
                        </Button>
                      )}
                      <Button
                        disabled={busy}
                        onClick={() =>
                          setPolicyAction({ id: policy.id, revoke: true })
                        }
                      >
                        Révoquer la règle
                      </Button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          <div className="pagination"><Button disabled={policyPage === 1} onClick={() => setPolicyPage(policyPage-1)}>Précédent</Button><span>Page {policyPage} · 100 règles maximum par page</span><Button disabled={!policies.data || policies.data.length < 100} onClick={() => setPolicyPage(policyPage+1)}>Suivant</Button></div>
        </section>
      ) : (
        <section className="card workspace-card">
          <h2>Schémas réellement inspectés</h2>
          <p className="availability-note">
            En-têtes et positions stricts. La colonne sans libellé reste
            conservée en staging. Deux colonnes Identifiant des personnes
            physiques sont distinguées par leur position. Les identifiants
            numériques et dates ambiguës sont rejetés.
          </p>
          {Object.entries(templates).map(([key, spec]) => (
            <details className="template-detail" key={key}>
              <summary>
                {templateLabels[key]} · feuille {spec.sheet} ·{" "}
                {spec.headers.length} colonnes · v{spec.version}
              </summary>
              <ol>
                {spec.headers.map((label, i) => (
                  <li key={i}>
                    {i + 1} · {label ?? "Sans libellé"}
                    {spec.candidate_keys.includes(i + 1)
                      ? " — clé candidate, règle explicite requise"
                      : ""}
                  </li>
                ))}
              </ol>
            </details>
          ))}
        </section>
      )}
      {policyForm && (
        <DataEditor
          title="Proposer une règle de publication"
          description={`${templateLabels[template]} · snapshots immuables seulement. Justifiez le sens et l’unicité de la clé choisie. Une autre personne devra approuver cette règle. Aucun lien client automatique.`}
          fields={[
            {name: "data_scope", label: "Usage de la règle", required: true, options: [{value: "", label: "Choisir explicitement"}, {value: "synthetic", label: "Données synthétiques de test"}, {value: "operational", label: "Données opérationnelles · approbation métier requise"}]},
            {
              name: "key_column",
              label: "Colonne clé explicitement validée",
              options: templates[template].candidate_keys.map((position) => ({
                value: String(position),
                label: `${position} · ${templates[template].headers[position - 1]}`,
              })),
            },
            {
              name: "rationale",
              label:
                "Justification de propriété et d’unicité (20 caractères minimum)",
              type: "textarea",
              maxLength: 1000,
            },
            {
              name: "date_format",
              label: "Interprétation des dates à approuver",
              options: [
                { value: "ISO", label: "ISO · année-mois-jour" },
                { value: "DMY", label: "Jour/mois/année · explicite" },
              ],
            },
          ]}
          initial={{ date_format: dateFormat, data_scope: dataScope }}
          close={() => setPolicyForm(false)}
          save={async (values) => {
            const saved = await importApi.policy(org.id, {
              template,
              key_column: Number(values.key_column),
              rationale: values.rationale,
              date_format: values.date_format,
              data_scope: values.data_scope,
              template_version: templates[template].version,
            });
            setPolicyView(saved.approved_at ? "approved" : "pending");
            setPolicyPage(1);
            await refresh();
          }}
        />
      )}
      {policyAction && (
        <Dialog
          title={
            policyAction.revoke ? "Révoquer la règle" : "Approuver la règle"
          }
          onClose={() => !busy && setPolicyAction(null)}
        >
          <p>
            Cette décision est auditée.{" "}
            {policyAction.revoke
              ? "Les publications futures avec cette règle seront bloquées."
              : "La règle autorisera uniquement des snapshots source immuables, sans mise à jour de client ni de compte."}
          </p>
          <p className="micro mt-4">Règle : {policyAction.id}</p>
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="editor-actions">
            <Button disabled={busy} onClick={() => setPolicyAction(null)}>
              Annuler
            </Button>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  await importApi.approve(
                    org.id,
                    policyAction.id,
                    policyAction.revoke,
                  );
                  setPolicyView(policyAction.revoke ? "history" : "approved");
                  setPolicyPage(1);
                  setPolicyAction(null);
                })
              }
            >
              Confirmer la décision
            </Button>
          </div>
        </Dialog>
      )}
      {confirm && selected && (
        <Dialog
          title="Revue avant publication"
          onClose={() => !busy && setConfirm(false)}
        >
          <p>
            {selected.total} lignes, {selected.rejected} rejet(s). Source :{" "}
            {templateLabels[selected.template]} au {selected.source_as_of}.
          </p>
          <p className="source-rule-notice">
            Cette action publie des snapshots immuables. Aucun attribut de
            client ou compte Carthago n’est remplacé. Aucune absence ne provoque
            de suppression.
          </p>
          <label className="organization-select">
            Règle approuvée
            <select
              aria-label="Règle approuvée"
              value={effectivePolicyId}
              onChange={(e) => setPolicyId(e.target.value)}
            >
              <option value="">Choisir une règle active</option>
              {activePolicies
                .map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    Colonne {policy.key_column} ·{" "}
                    {policy.rationale.slice(0, 70)}
                  </option>
                ))}
            </select>
          </label>
          {selected.rejected > 0 && (
            <label className="preview-actions">
              <input
                type="checkbox"
                checked={exclude}
                onChange={(e) => setExclude(e.target.checked)}
              />
              J’exclus explicitement les {selected.rejected} lignes rejetées ;
              seules les lignes valides seront publiées.
            </label>
          )}
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="editor-actions">
            <Button disabled={busy} onClick={() => setConfirm(false)}>
              Annuler
            </Button>
            <Button
              variant="primary"
              disabled={
                busy || preview.isFetching || preview.isError || publicationBlocks.length > 0 || !effectivePolicyId || (selected.rejected > 0 && !exclude)
              }
              onClick={() =>
                void perform(async () => {
                  await importApi.publish(
                    org.id,
                    selected.id,
                    effectivePolicyId,
                    exclude,
                  );
                  setConfirm(false);
                })
              }
            >
              Confirmer la publication
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}
