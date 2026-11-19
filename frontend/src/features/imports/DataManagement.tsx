import { useState, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, ShieldCheck, Database, Download } from "lucide-react";
import { Badge, Button, Dialog, StatePanel } from "../../components/ui";
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
  const [tab, setTab] = useState("imports"),
    [sourceDate, setSourceDate] = useState(today()),
    [snapshot, setSnapshot] = useState("partial");
  const [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [batch, setBatch] = useState<Batch | null>(null),
    [page, setPage] = useState(1),
    [batchPage, setBatchPage] = useState(1),
    [rejected, setRejected] = useState(false);
  const [confirm, setConfirm] = useState(false),
    [exclude, setExclude] = useState(false);
  const batches = useQuery({
    queryKey: ["import-batches", auth.identity?.session.id, org.id, batchPage],
    queryFn: () => importApi.batches(org.id, batchPage),
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
  const job = useQuery({
    queryKey: ['synthetic-import-job', auth.identity?.session.id, org.id, selected?.id],
    queryFn: () => importApi.syntheticJob(org.id, selected!.id),
    enabled: !!selected && selected.status === 'published' && selected.data_scope === 'synthetic',
    refetchInterval: query => query.state.data?.status === 'complete' ? false : 3000,
    retry: false,
  });
  const publicationBlocks = selected?.status === 'staged' ? [
    ...(selected.data_scope === 'legacy' && !preview.data?.legacy_rule_unique ? ['Aucune règle historique approuvée unique : redéposez le fichier en choisissant explicitement son usage pour le revalider.'] : []),
    ...(!org.approve ? ['Votre habilitation ne permet pas la publication. Un réviseur autorisé doit intervenir.'] : []),
    ...(selected.uploaded_by_id === auth.identity?.session.id ? ['Le déposant ne peut pas publier son propre lot : une revue par un autre utilisateur habilité est obligatoire.'] : []),
    ...(preview.isPending || preview.isFetching ? ['Chargement et validation des exigences de publication...'] : preview.isError ? ['Examen inaccessible : publication bloquée. Rechargez les détails.'] : []),
    ...(selected.total === selected.rejected ? ['Aucune ligne valide : corrigez le fichier puis déposez un nouveau lot. Le staging existant reste conservé.'] : []),
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
      await refresh();
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
            Les imports synthétiques sont synchronisés en arrière-plan après
            publication. Les données opérationnelles restent séparées du CRM.
          </p>
        </div>
      </div>
      <nav className="workspace-tabs" aria-label="Gestion des données">
        {[
          ["imports", "Imports & historique"],
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
                      "",
                      sourceDate,
                      snapshot,
                      "DMY",
                      dataScope,
                    );
                    choose(result);
                  });
                }}
              >
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
              <p>{selected.data_scope === 'legacy' ? 'Lot historique : utilisation de la règle historique approuvée unique, si disponible.' : `Configuration fixe v1 · identifiant colonne ${selected.template === 'accounts' ? 'E' : 'B'}`}</p>
              <p className="digest">
                Usage : {selected.data_scope === 'synthetic' ? 'Synthétique' : selected.data_scope === 'operational' ? 'Opérationnel' : 'Historique non classifié'} · Schéma v{selected.template_version} ·{' '}
                SHA-256 : {selected.digest} · Format des dates :{" "}
                {selected.date_format}
              </p>
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
                  {selected.status === 'published' ? <p>Publié le {selected.published_at ? formatDate(selected.published_at) : '—'} · réviseur : {selected.published_by_id} · règle : {selected.policy_id}. {selected.published_rows} snapshot(s) conservé(s). {selected.data_scope === 'synthetic' ? 'La synchronisation de test est suivie ci-dessous.' : 'Aucun compte ni client opérationnel créé.'}</p> : <><p>La validation technique ne vaut pas approbation métier. Le dépôt n’est jamais publié automatiquement.</p>{publicationBlocks.length > 0 ? <ul>{publicationBlocks.map(reason=><li key={reason}>{reason}</li>)}</ul> : <p>La configuration fixe est disponible. Un réviseur autorisé peut examiner puis confirmer explicitement la publication.</p>}</>}
                </div>
              </section>
              {selected.status === 'published' && selected.data_scope === 'synthetic' && <p role="status" className="availability-note">{job.isError ? 'État de synchronisation indisponible.' : job.data?.status === 'complete' ? `Synchronisation terminée · ${job.data.processed} ligne(s) traitée(s).` : job.data?.status === 'blocked' ? `Synchronisation en attente · ${job.data.last_error} Une nouvelle tentative sera effectuée automatiquement.` : `Synchronisation en cours ou en attente · ${job.data?.processed ?? 0} ligne(s) traitée(s).`}</p>}
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
      {confirm && selected && (
        <Dialog
          title="Revue avant publication"
          onClose={() => !busy && setConfirm(false)}
        >
          <p>
            {selected.total} lignes, {selected.rejected} rejet(s). Source :{" "}
            {templateLabels[selected.template]} au {selected.source_as_of}.
          </p>
          {selected.data_scope === 'synthetic' && <p>Après publication, les données de test seront synchronisées en arrière-plan par identifiant source.</p>}
          <p className="source-rule-notice">
            Cette action publie des snapshots immuables. Aucun attribut de
            client ou compte Carthago n’est remplacé. Aucune absence ne provoque
            de suppression.
          </p>
          <p>{selected.data_scope === 'legacy' ? 'La règle historique approuvée unique sera utilisée.' : `Configuration fixe : ${templateLabels[selected.template]} · colonne ${selected.template === 'accounts' ? 'E' : 'B'} · version 1`}</p>
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
                busy || preview.isFetching || preview.isError || publicationBlocks.length > 0 || (selected.rejected > 0 && !exclude)
              }
              onClick={() =>
                void perform(async () => {
                  await importApi.publish(
                    org.id,
                    selected.id,
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
