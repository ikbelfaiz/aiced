# S15 — Segmentation descriptive et qualité technique CRM

## Données disponibles et limites

Inspection des modèles `Party`, `PhysicalPerson`, `LegalEntity`, `CRMProfile`,
`ExternalIdentity`, `FinancialAccount`, des vues Client/Workspace, du backlog
et de l'analyse fonctionnelle, avant modification. Les données de recette
sont synthétiques ; aucune extraction Carthago ni donnée client réelle importée.

| Dimension | État dans cet incrément |
|---|---|
| Type | `Party.kind` : physique/morale seulement, options/effectifs visibles dynamiques. Aucune classe VIP ou institutionnel déduite |
| Profession / secteur | Champs CRM existants, correspondance exacte, variantes conservées ; filtres présence/absence existants |
| Complétude / information absente | Nouveaux filtres techniques sur email/téléphone/profession/secteur CRM |
| Âge | Indisponible : aucune date de naissance opérationnelle fiable |
| Revenus / tranches | Indisponible : aucun champ opérationnel ni définition approuvée |
| Risque / investissement / VIP | Indisponibles : classifications, mappings et politiques non validés |
| Produit | Le libellé de compte projeté n'est pas une classification produit validée ; aucun segment financier inféré |

Un profil CRM absent, une valeur nulle, vide ou composée uniquement d'espaces
reconnus par PostgreSQL sont absents (`IS NULL OR ~ '^\s*$'`). Le même prédicat
sert aux calculs, filtres, compteurs et à la fiche. Les libellés d'options restent
bruts, avec casse et espaces. Diagnostic seulement : groupes de variantes selon
`lower(trim(valeur))` (espaces ordinaires pour trim) et effectifs avec espaces
en bordure. Aucun nettoyage ni rapprochement d'identités, aucune fusion.
Le diagnostic n'affirme pas que deux catégories sont équivalentes.

## Définition technique provisoire

Par défaut : `email,phone,profession,sector`, **champs CRM AICED uniquement**.
Pourcentage = partie entière de `100 × champs présents / champs configurés`.
Poids égaux, sans obligation métier, validation de la valeur, pertinence par
type de personne ni appréciation KYC/conformité. Notes et informations
financières exclues. Un profil absent vaut 0 %, pas une identité invalide.
Une population vide compte zéro profil complet/incomplet, sans moyenne inventée.

Variable de processus Client `AICED_PROFILE_COMPLETENESS_FIELDS` : liste séparée
par virgules de ces seuls quatre noms, sans doublon. Définition non persistée,
adaptable par la configuration du processus ; aucune modification Compose.
Chaîne vide : évaluation indisponible, pourcentage/effectifs de complétude nuls,
contrôles désactivés et filtres d'intervalle refusés (400). Une configuration
invalide échoue explicitement ; ne pas utiliser des attributs source non validés.
AMEN INVEST doit approuver pertinence, applicabilité et politique avant de
présenter une définition métier. Les champs source restent en lecture seule,
leur qualité non calculable tant que le mapping n'est pas validé.

## Interface et API

`/clients` : filtres combinables, intervalle inclusif 0–100, information absente,
recherche/type/tri/pagination existants ; suppression individuelle et remise à
zéro, sélection conservée dans l'URL, changement de filtre remet la page à 1.
Le compteur du segment est celui de la liste filtrée. Le résumé qualité, les
options et leurs effectifs portent sur **tous les clients visibles avant
filtrage**, jamais uniquement sur la page. Prospects exclus du Panorama.

Client 360 `/clients/:id` : pourcentage provisoire, champs absents, distinction
CRM AICED éditable avec habilitation / Carthago source en lecture seule.
Une erreur de ressource masque les anciennes options/statistiques/évaluation.
Aucun formulaire de correction source. Les flux d'édition CRM existants restent
les seuls écrivains ; ils invalident la qualité à changement de version.

* `GET /api/clients/` : paramètres optionnels supplémentaires
  `completeness_min`, `completeness_max` (entiers 0–100, min ≤ max),
  `missing_field` (`email|phone|profession|sector`). Réponse inchangée.
* `GET /api/clients/filter-options/` : réponses existantes profession/secteur
  conservées, ajouts `kind`, `quality` et `truncated`. Maximum 500 libellés par
  dimension, ordre déterministe, indication explicite de troncature ; les filtres
  exacts existants restent utilisables au-delà du catalogue affiché.
* `GET /api/clients/{party_id}/quality/` : nouvelle lecture objet uniquement.

Toutes les requêtes partent de `client_queryset(clients.view)` avant agrégats,
options, filtres, pagination ou détail. Calcul SQL, aucun chargement de toute
la population en mémoire. Diagnostics SQL supplémentaires proportionnels au
volume visible : pas de certification de débit sous charge. Autorisation IAM
signée existante, session fraîche et refus par défaut conservés. Aucun nouveau
writer, migration, rôle SQL, service, table, credential ou outbox. Les écritures
CRM existantes conservent leurs transactions et audit/outbox.

Baseline historique immuable ; extension revue des paramètres et nouvelle route
de lecture dans `contracts/additions.py`. Schémas historiques inchangés.

## Recette reproductible

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/client_quality.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
$env:AICED_E2E_SCALE='1'
try { python scripts/compose_browser.py --test } finally { Remove-Item Env:AICED_E2E_SCALE }
python scripts/compose_quality_restart.py --test
python scripts/compose_inventory.py --test
```

Les sondes de révocation et de redémarrage s'exécutent séparément du navigateur.
Rapports privés exclus dans `.local/compose-test/`. Les résultats effectifs et
le bilan de données synthétiques sont consignés après exécution ci-dessous.

## Fichiers de cet incrément

- Backend : `clients/quality.py`, `clients/segmentation.py`,
  `clients/tests_quality.py`, `config/urls.py`, `contracts/additions.py`.
- Frontend : `features/clients/{ClientsPage,ClientWorkspace,SegmentationFilters,ProfileQuality}.tsx`,
  `lib/api.ts`, `workspace.css`, `e2e/quality.spec.ts`, `e2e/screens.spec.ts`.
- Recette : `infra/acceptance/client_quality.py`, `scripts/compose_quality_restart.py`.
- Documentation : ce rapport, analyse fonctionnelle, backlog et questions ouvertes.

`screens.spec.ts` ne sélectionne plus une option « personne morale » inexistante
dans le périmètre synthétique du manager. Il vérifie son absence, puis utilise
le filtre URL `type=legal` pour conserver le contrôle du résultat vide serveur.
Le test ne crée pas une catégorie sans dossier visible.

## Résultats effectifs — Docker isolé

- Engine Docker **29.9.3**, sept conteneurs applicatifs sains et quatre processus
  Django distincts ; initialisation one-shot terminée normalement. Inventaire
  après redémarrage PostgreSQL : credentials propres, DNS interne et seul port
  Gateway publié. Huit configurations historiques/actuelles validées ; projets,
  volumes et credentials principal/test distincts. Aucun YAML Compose modifié.
- **206 tests backend réussis** : général 175 (dont six nouveaux tests qualité),
  IAM 5, Integration 8, Commercial 18. Logs et `regression-report.json` privés.
- **30 tests Chromium réussis, un ignoré**, zéro échec à l'exécution finale
  compilée via Nginx. Inclut les deux nouveaux parcours qualité, segmentation,
  Client 360, révocation, uploads/publication, agenda, campagnes et pipeline
  synthétique de 10 000 opportunités. Capture mobile qualité inspectée ; absence
  de débordement de page vérifiée par le navigateur.
- Première exécution : 28 réussis, deux échecs, un ignoré. Un filtre du grand
  pipeline a renvoyé 503 (limite opérationnelle S13 conservée) pendant une
  exécution concurrente des régressions backend. La suite complète exécutée
  ensuite sans ces régressions concurrentes passe, sans modification du pipeline
  ni élargissement des délais/protections. La concurrence n'est pas une preuve
  certaine de la cause du 503 ; aucune certification de débit n'en est déduite.
  L'autre échec était l'ancienne hypothèse d'option « personne morale » décrite
  ci-dessus. Rapport initial conservé : `s15-browser-initial.json/.log`.
- **Quatre groupes de sondes qualité** : vrais appels Nginx/Client/IAM,
  périmètre avant effectifs, objets masqués 404/IT 403, validations, révocation
  des permissions et expiration de session existante sans données protégées.
- **15 sondes d'intégration existantes réussies** : isolement des quatre
  credentials/historiques, courses d'autorisation, signatures/rejeu, conflits,
  rollback journal/outbox et livraison d'audit dédupliquée.
- **49 routes / 62 couples méthode-route** contrôlés. OpenAPI réel comparé à la
  baseline historique inchangée avec les seuls ajouts revus.
- **Redémarrage réel PostgreSQL réussi** : même session, page triée/filtrée,
  options/compteurs/diagnostics et fiche qualité identiques avant/après.
- `makemigrations --check --dry-run` : aucun changement ; `git diff --check`
  sans erreur de contenu. Build TypeScript/Vite compilé réussi.

Inventaire **strictement synthétique**, dernière sonde : lecteur A, quatre
clients autorisés, quatre absences pour chacun des quatre champs ; opérateur A,
181 clients visibles, email absent 160, téléphone absent 181, profession absente
41, secteur absent 77. Aucun profil à 100 %, aucun groupe de variantes dans ce
périmètre de recette. Ces chiffres évoluent avec les créations des tests et ne
décrivent pas AMEN INVEST. Les tests unitaires séparés injectent expressément
des variantes de casse/espaces, profils absents et population vide pour vérifier
ces cas ; aucun rapprochement de personnes n'est effectué.

La recette est une validation locale synthétique. Sources Carthago, taxonomies,
complétude métier et préparation production restent à valider séparément.

La stack principale a ensuite été reconstruite/démarrée avec
`docker compose up --build -d --wait --wait-timeout 180`, puis le Gateway
redémarré pour rafraîchir ses résolutions DNS après remplacement des conteneurs.
Sept conteneurs sains, inventaire principal réussi. Smoke authentifié en lecture
seule à `http://127.0.0.1:5187` : page `/clients`, options, liste avec intervalle
et détail qualité répondent 200. Les mutations, révocations et redémarrage de
recette ont été exécutés uniquement dans le projet test isolé sur le port 5188.

## Suite métier

Priorité suivante : **descriptif d'activité commerciale puis tableaux CRM
managériaux**, avec dictionnaire de mesures, périodes et matrice de direction
approuvés. Aucun revenu réalisé, encours, taux de conversion ou score inféré.
Restent à confirmer par AMEN INVEST : nomenclatures profession/secteur/types,
définition de complétude applicable aux personnes physiques/morales, gouvernance
des corrections, identité/mappings source, accès aux attributs sensibles.
