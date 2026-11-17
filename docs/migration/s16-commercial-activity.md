# S16 — Activité commerciale CRM

## Définitions retenues après inspection

Inspection du backlog et de l'analyse fonctionnelle S15, des modèles Interaction,
Prospect, Appointment, Opportunity, CampaignDraft, des vues history/followups/agenda,
du pipeline S13 et des brouillons S14. Le dashboard existant contient des
illustrations de maquette et des indicateurs indisponibles : il n'est pas utilisé
comme source. S16 ajoute une page opérationnelle distincte, sans réécrire les
maquettes ni attribuer des droits de direction.

| Mesure | Source propriétaire et population | Date / définition | Limites |
|---|---|---|---|
| Interactions par type / total / jour | Client Interaction ; intersection `clients.view` et `interactions.view` sur les dossiers, avec visibilité prospect existante | `occurred_at`, date déclarée ; début local inclus, lendemain de fin exclu | Enregistrement CRM actuellement présent, pas preuve de contact, saisie du jour, productivité ou résultat ; aucune attribution au commercial déduite de l'auteur |
| Rendez-vous par type / total / jour | Client Appointment ; propriétaire = utilisateur courant, organisations autorisées par les permissions agenda existantes | `starts_at` dans la période, même si la fin déborde | Planification personnelle uniquement, chevauchements comptés séparément ; ni rendez-vous réalisé ni taux d'assiduité |
| Relances en retard / aujourd'hui / à venir / sans date | Client Prospect, `prospect_queryset` existant, intersection clients/prospects par objet | `next_action_date` comparée à la date métier au calcul, null = sans date | Instantané courant toutes dates/tous statuts, y compris clos comme la worklist ; le filtre de période/type ne s'applique pas. Pas d'historique ni rappel automatique |
| Opportunités par statut | Commercial API pipeline ; chaque dossier autorisé par Client via le contrat signé existant | Stock actuel `open/won/lost`, toutes dates | Aucun historique de statut fiable dans ce modèle ; période/type non appliqués ; aucun taux de conversion, montant ou revenu |
| Mes brouillons de campagnes | Commercial CampaignDraft, API S14 ; créateur courant seulement, organisations autorisées | Nombre actuel, toutes dates | S14 réellement présent ; aucun décompte de lancements, contacts ou modifications, aucune activité historique inférée de `updated_at` |
| Tendances CRM | Même périmètre que les interactions / rendez-vous | Deux séries journalières distinctes sur la période, zéros explicites | Distribution des dates des enregistrements actuels, pas historique immuable des changements ni performance |

Les mesures ci-dessus sont descriptives, autorisées dans S16 par l'utilisateur.
Une permission absente produit une section indisponible/null, jamais un zéro
présenté comme un résultat. Un périmètre autorisé vide produit de vrais zéros.
Aucun total synthétique n'additionne des unités de nature différente.

## Périodes et filtres

Le nouveau rapport Client utilise `AICED_REPORT_TIME_ZONE`, par défaut la valeur
configurable de l'agenda, elle-même `Africa/Tunis`. Validation IANA au démarrage.
Les dates sans heure sont des dates civiles dans ce fuseau ; le navigateur
n'utilise pas sa date locale pour choisir la période par défaut. Défaut : date
métier courante et 29 jours précédents. 1 à 93 jours inclusifs, années 1900–9998.
Les bornes sont construites séparément à minuit local pour respecter les jours
de 23/25 heures. Le graphique regroupe avec ce même fuseau PostgreSQL.

`date_from`, `date_to` et `kind=call|email|meeting|visit` s'appliquent uniquement
aux deux mesures périodiques. Le formulaire conserve les filtres dans l'URL et
propose une remise à zéro. Les stocks sont clairement séparés et étiquetés
« état actuel ». Pas de classement de collaborateurs, client actif, taux de
conversion ou formule financière. Les liens ouvrent les écrans existants sans
leur transmettre des filtres de fuseau incompatibles.
La configuration du rapport ne reconfigure pas les anciens écrans S8/S9, qui
restent explicitement à Tunis. Leurs comparaisons de compteurs sont vérifiées
avec le défaut Tunis ; un déploiement dans un autre fuseau doit faire approuver
et harmoniser ces conventions avant de présenter leurs périodes comme identiques.

## API, sécurité et limites de traitement

- Route frontend `/activite-commerciale`, navigation « Activité commerciale ».
- Nouvelle lecture Client `GET /api/clients/activity-report/`, paramètres ci-dessus.
  Aucun nouvel écrivain, aucune migration ou duplication de données.
- Lectures Commercial existantes : `GET /api/opportunities/?page_size=1` et
  `GET /api/campaigns/?page_size=1`. Le dashboard utilise leurs compteurs,
  jamais le nombre d'éléments de cette page ni une boucle de pages.
- Trois requêtes frontend au plus par chargement/actualisation, pas de polling
  de données métier. Les trois réponses ne forment pas un instantané distribué.
  Une erreur masque les chiffres en cache de la source concernée. Les autres
  sections restent identifiées par leur propre propriétaire/disponibilité.
- Scoping avant tout calcul, aucune lecture Commercial depuis les tables Client
  ni l'inverse. Rapport Client en `READ COMMITTED` : chaque métrique groupe date
  et type dans une seule requête, après l'admission. Séries et totaux proviennent
  de ce même agrégat (maximum 93 × 4 groupes). Aucun instantané SQL antérieur
  au verrou de visibilité n'est réutilisé. Les écrivains métier Client existants
  utilisent la barrière exclusive correspondante ; admission partagée IAM/Client
  non bloquante, revalidation
  signée fraîche avant/après, expiration/révocation/panne fermées. Trois appels
  IAM au plus par requête de rapport (authentification comprise), pas de cache
  d'autorisation interrequête. Budget du calcul après authentification : 4 s,
  délais SQL/HTTP ajustés au reste ; aucun résultat partiel sur dépassement.
- Agrégats SQL, quatre types et 93 jours au plus ; mémoire frontend/backend
  bornée. Pas de pagination de ce petit agrégat. Le pipeline conserve son
  parcours autorisé S13 par lots et son budget 4 s : coût linéaire dans les
  opportunités candidates, possibilité de 503 sous charge. S16 n'augmente pas
  ses plafonds ou privilèges. Aucun débit de production certifié.
- Audit/outbox des écrivains existants inchangés. Les rapports sont des lectures,
  ne produisent pas de nouveaux événements métier. Carthago reste en lecture seule.
  Compose, quatre services, rôles/schémas/migrations et secrets inchangés.

## Vérification

Résultats effectifs sur la stack Docker isolée :

- **214 tests backend réussis** : général 183 (dont huit nouveaux tests rapport),
  IAM 5, Integration 8, Commercial 18. Calculs, frontières minuit Tunis,
  journée DST New York, maximum 93 jours, jeux vides, droits partiels, périmètre
  objet, propriétaire d'agenda, expiration et budget dépassé vérifiés.
- Régression de concurrence déterministe : une réaffectation commit entre les
  deux admissions. Le test échoue effectivement sur la première version S16 en
  `REPEATABLE READ` (ancien effectif visible 2 au lieu de 0) et passe avec les
  agrégats `READ COMMITTED` après clôture d'admission. Aucun ancien instantané
  du périmètre Client ne survit à cette réaffectation. Preuve privée :
  `s16-old-snapshot-regression.log`. Vérification finale rejouée après correction.
- **33 tests Chromium réussis, un ignoré**, zéro échec final : trois nouveaux
  parcours reporting, cartes comparées aux vraies API, valeurs du graphique,
  filtrage et rechargement en navigateur Los Angeles, date invalide/erreurs,
  refus IT, reprises, navigation vers l'historique. Les suites agenda/campagnes,
  Client 360, qualité/segmentation, imports/publication et pipeline 10 000 sont
  incluses. Capture mobile inspectée ; débordement horizontal exclu par test.
- Premier passage complet : 32 réussis, un échec, un ignoré. Le test avait
  oublié de rouvrir le détail du graphique après rechargement ; correction du
  test, sans modification du calcul ni de ses seuils. Passage complet final
  réussi. Rapport initial conservé dans `s16-browser-initial.json/.log`.
- **Quatre groupes de sondes reporting réelles** : oracle SQL et limites de date,
  exclusion d'interactions de dossiers masqués de la même organisation, IT 403,
  rendez-vous d'autrui exclus, relances identiques à la worklist autorisée,
  absence d'écriture journal/outbox, rôle révoqué et session expirée refusés.
- **15 sondes d'intégration existantes réussies** : quatre credentials restreints,
  quatre historiques de migrations, autorisations concurrentes, signatures/rejeu,
  rollback journal/outbox et livraison d'audit dédupliquée.
- **Quatre contrôles de reprise réels** : arrêt Client, Commercial, IAM ; les
  sources dépendantes échouent sans compteurs, les sources indépendantes restent
  disponibles. Redémarrage PostgreSQL et reprise avec la même session : séries,
  compteurs et objets Commercial identiques, hors heure de génération du rapport.
- **50 routes / 63 couples méthode-route**, baseline historique et OpenAPI réel
  compatibles avec le seul ajout S16. `makemigrations --check --dry-run` : aucun
  changement ; build TypeScript/Vite réussi, `git diff --check` sans erreur.
- Sept conteneurs applicatifs sains, quatre processus Django distincts, seul
  Gateway exposé ; validation des huit configurations et de la séparation
  projet/volume/credentials entre principal et test réussie. Aucun Compose,
  Dockerfile, schéma, propriétaire SQL ou migration modifié en S16.

Rapports privés : `regression-report.json`, `browser-compiled/report.json`,
`activity-report.json`, `activity-recovery-report.json`, `integration-report.json`,
`routes-report.json` dans `.local/compose-test`. Toute mutation/révocation/panne
de recette s'exécute sur les données synthétiques du projet test isolé.
Ces résultats ne constituent pas une certification de production ou de KPI
financiers/managériaux.

Après la correction de concurrence, les suites backend, sondes reporting,
contrats/intégration, arrêts/reprises et la suite Chromium complète ont été
rejoués avec succès sur l'image corrigée. Engine réellement disponible :
**29.9.3**. La stack principale a été reconstruite, Gateway redémarré pour ses
résolutions DNS, puis attendue saine : sept conteneurs et quatre processus Django.
Smoke authentifié en lecture seule à `http://127.0.0.1:5187` :
`/activite-commerciale` et les trois API utilisées répondent 200 ; code Client
déployé vérifié en `READ COMMITTED`. Aucune fixture, révocation ou panne de recette
n'a été appliquée au projet principal.

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/activity_report.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
$env:AICED_E2E_SCALE='1'
try { python scripts/compose_browser.py --test } finally { Remove-Item Env:AICED_E2E_SCALE }
python scripts/compose_activity_recovery.py --test
python scripts/compose_inventory.py --test
python scripts/compose_validate.py
```

Exécuter les sondes de révocation/panne et le navigateur séparément. Les suites
backend utilisent des bases de test transitoires distinctes ; ne pas les lancer
simultanément au parcours navigateur de capacité si l'hôte est chargé.
Fixtures métier synthétiques uniquement, rapports et captures privés exclus.

Fichiers : `backend/clients/reporting.py`, `tests_reporting.py`,
`backend/iam_consumer/access.py` (délai optionnel compatible du snapshot IAM),
`backend/config/{settings,urls}.py`, `backend/contracts/additions.py` ;
`frontend/src/features/reporting/CommercialActivity.tsx`, `app/App.tsx`,
`components/layout/AppShell.tsx`, `workspace.css`, `frontend/e2e/activity.spec.ts` ;
`infra/acceptance/activity_report.py`, `scripts/compose_activity_recovery.py` ;
ce rapport, backlog, analyse fonctionnelle et questions ouvertes.

## Décisions métier et suite

Les champs et droits actuels suffisent à la vue opérationnelle personnelle /
périmètre CRM existant. AMEN INVEST doit approuver toute matrice de direction,
visibilité d'équipe, attribution auteur/responsable, définition de résultats,
objectifs ou ratios avant S17. Les KPI financiers restent bloqués par les
sources/mappings et formules approuvés, indépendamment de ces compteurs CRM.
Priorité suivante : **S17 — tableau de bord CRM managérial**, uniquement sur
mesures vérifiées et agrégations autorisées ; aucun accès global implicite.
