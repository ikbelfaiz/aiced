# S11 — COM-03, pipeline des opportunités

## Parcours livré

`/opportunites` et la navigation « Opportunités » ouvrent un Kanban des statuts
existants : Ouvertes, Gagnées, Perdues. Recherche dossier/titre/notes, filtre
statut, tri et pagination sont conservés dans l'URL. Les colonnes représentent
les cartes de la page courante ; les compteurs autorisés portent sur tous les
résultats après recherche, avant filtre de statut. Il n'y a aucun total de
montants, taux, score ou probabilité.

Une carte affiche titre, nom de dossier reçu de Client, estimation manuelle
exacte TND ou absence explicite, échéance et notes. L'estimation n'est jamais
présentée comme un revenu ou un encours. Sur mobile, les colonnes s'empilent.
Les erreurs masquent les cartes et compteurs précédents, avec reprise explicite.

La création reste dans la fiche Client 360 existante. Le lien d'une carte ouvre
`/clients/{party_id}?onglet=opportunities&opportunite={id}` : le GET détail
existant charge précisément cette opportunité, indépendamment de la pagination
du dossier. Son éditeur existant assure les changements de statut, sans glisser-
déposer, nouveau workflow ou nouvelle règle de transition. Lien vers toutes les
opportunités du dossier et retour au pipeline disponibles. Sans paramètre
`opportunite`, la fiche conserve son comportement historique.

## API et frontières

Nouvelle lecture publique Commercial : `GET /api/opportunities/`.

| Paramètre optionnel | Valeurs |
|---|---|
| `search` | Titre/notes/nom du dossier autorisé, 200 caractères maximum |
| `status` | `open`, `won`, `lost` ; absent = tous |
| `ordering` | `-updated_at` (défaut), `updated_at`, `title`, `-title`, `due_date`, `-due_date` |
| `page`, `page_size` | Page à partir de 1 ; taille 1–50, défaut 8 |

Réponse paginée habituelle (`count`, `next`, `previous`, `results`) plus
`statuses` (effectifs open/won/lost avant filtre de statut). Chaque résultat
contient les champs existants de l'opportunité, `party_id`, `party_name` et
`can_edit`. UUID départage les égalités ; échéances absentes en dernier dans
les deux sens. Aucun endpoint de mutation supplémentaire.

Client & CRM ajoute uniquement le contrat privé HMAC
`POST /internal/v1/clients/opportunity-scope`, réservé au service Commercial
et à l'audience `client`, avec les identités pair-à-pair existantes. Il reçoit
les credentials de session et au plus 100 UUID candidats ; il renvoie seulement
les IDs/noms autorisés et la possibilité d'édition. `clients.view` et
`opportunities.view` s'intersectent sur chaque objet, avec les restrictions
prospects existantes. `can_edit` ne confère aucun droit : PATCH revalide tout.

Commercial ne consulte que son ORM et ses références locales ; les décisions
d'objet et noms viennent de Client par HTTPS signé. Les réponses sont validées
(acteur, IDs demandés, unicité, bornes, noms et booléens), sans cache de décisions.
Les filtres métier, effectifs et pagination s'appliquent ensuite aux seuls IDs
autorisés. Un dernier appel IAM revalide la session avant réponse. L'absence
de capacité est refusée même sans opportunité ; panne ou réponse invalide d'un
pair ferme l'accès, sans résultat partiel ni fallback.

Pour borner le fan-out synchrone, ce MVP accepte au plus **500 références de
dossier distinctes dans le stockage d'opportunités Commercial**, tous périmètres
confondus. Au-delà, 503 explicite, jamais une troncature ou un compteur partiel.
Un contrat de périmètre paginé plus extensible sera nécessaire pour dépasser
cette limite. Les lots privés restent de 100 maximum.

Nginx ajoute une seule entrée de routage exact vers Commercial. Le schéma
public utilise un contrat sans modèle de persistance ; une requête pipeline
directement adressée au runtime Client échoue, elle ne sert jamais une liste
monolithique de remplacement. Les 38 routes historiques restent intactes ;
avec les lectures S8–S11 : 42 routes publiques, 51 couples méthode/route.
La baseline OpenAPI n'est pas régénérée et tous les champs existants restent
compatibles.

## Sécurité et invariants

Sessions IAM, révocation, CSRF délégué, signatures/audiences/nonces et refus par
défaut sont conservés. Les mutations passent par l'ancien endpoint autorisé
`PATCH /api/clients/{party_id}/opportunities/{id}/` avec version obligatoire,
verrou et conflit 409. Journal et outbox restent dans la même transaction.
Client n'acquiert aucun modèle Commercial ; Commercial n'acquiert aucun modèle
Client/IAM. Aucun schéma, migration, secret, volume, réseau, port ou fichier
Compose n'est modifié. Carthago demeure strictement en lecture seule.

## Recette Docker du 15 novembre 2026

Application reconstruite dans le projet isolé `aiced-test`, accès Chromium →
Nginx → services → PostgreSQL, aucun serveur local de substitution. Docker
Engine 29.9.3 / Compose v5.7.0 réellement disponibles.

| Vérification | Résultat final |
|---|---|
| Régression générale | 160 tests réussis, dont 3 nouveaux tests Client/HMAC/scoping |
| IAM / Integration / Commercial propres | 5 / 8 / 7 tests réussis ; Commercial inclut 2 nouveaux tests de confiance/lot borné ; total backend 180 |
| Chromium compilé | 21 réussis, 1 ignoré car maquettes réservées au développement ; aucun échec final |
| Deux nouveaux workflows navigateur | Création réelle, pipeline, détail précis, changement de statut, conflit après édition concurrente, pagination/tri/rechargement/mobile ; refus IT, erreur et reprise sans cache affiché |
| Sondes réelles pipeline | 5 contrôles réussis : scope assigné/inter-organisations avant comptes/pages, filtres, deux PATCH simultanés (200/409), une seule paire journal/outbox, refus lecture seule/révocation et session expirée |
| Pannes physiques Client et IAM | Aucune ligne ni compteur pendant chaque arrêt ; même session et réponse identique après reprise |
| Redémarrage Commercial | Même session, opportunités/versions/compteurs identiques |
| Sondes historiques quatre services | 15 contrôles : isolation SQL, concurrence/révocation, signatures/rejeu, rollback audit/outbox, livraison dédupliquée et audit fédéré |
| Contrats/routes | OpenAPI compatible ; 42 routes/51 couples méthode-route, anonyme et routes retirées refusés |
| Migrations | `makemigrations --check --dry-run` : aucun changement ; `migrate --check` réussi |
| Compose | Parité 8 configurations, séparation test des volumes et credentials ; 7 conteneurs sains, quatre processus Django indépendants |

Les tests Client ont d'abord échoué en 404 avant l'ajout du contrat privé,
puis passent avec contrôle signature/rejeu, scoping croisé et restriction prospect.
La première sonde pipeline a passé ses assertions mais son nettoyage a été
refusé par la protection d'immutabilité des références Commercial. Aucune
protection n'a été désactivée : la sonde conserve désormais ses enregistrements
synthétiques et journaux dans la base jetable, supprime ses droits temporaires
et a été relancée avec succès. Les fixtures de l'essai initial restent
synthétiques avec droits révoqués. Le contrôle des routes lancé pendant l'arrêt
IAM a rencontré le 504 attendu ; il a été relancé après reprise et passe.

Les captures mobile ont été inspectées. Les erreurs injectées Playwright
vérifient l'interface ; les arrêts physiques sont prouvés séparément par le
script de récupération. Les rapports privés restent dans `.local/compose-test`.

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
python scripts/compose_browser.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/pipeline.py
python scripts/compose_pipeline_recovery.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_validate.py
python scripts/compose_inventory.py --test
```

Exécuter les sondes de révocation, les pannes et les suites navigateur/routes
séquentiellement, sur la seule base synthétique isolée.

## Fichiers S11

- Backend : `commercial/pipeline_contract.py`, `commercial_service/pipeline.py`,
  `commercial_service/tests_pipeline.py`, `commercial_service/urls.py`,
  `clients/pipeline_scope.py`, `clients/tests_pipeline_scope.py`,
  `iam_consumer/urls.py`, `config/urls.py`, `contracts/additions.py`,
  `service_architecture/ownership.py` (tous sous `backend/`).
- Frontend : `frontend/src/features/opportunities/OpportunityPipeline.tsx`,
  `frontend/src/features/clients/ClientWorkspace.tsx`, `frontend/src/app/App.tsx`,
  `frontend/src/components/layout/AppShell.tsx`, `frontend/src/workspace.css`,
  `frontend/e2e/pipeline.spec.ts`.
- Routage/validation : `infra/gateway/nginx.conf.template`,
  `infra/acceptance/pipeline.py`, `infra/acceptance/verify.py`,
  `scripts/compose_pipeline_recovery.py`.
- Documentation : ce rapport, `docs/functional-gap-analysis.md`, `docs/mvp-backlog.md`.

Les changements S7–S10 déjà présents dans l'espace de travail sont conservés.

## Limites et suite

Pas d'étape configurable, responsable commercial distinct, produit structuré,
historique d'évolution, taux de conversion, score, KPI ou valeur financière
déduite. Pas de changement de statut directement dans le Kanban. Les limites
de déploiement S7/S8 demeurent ; la recette locale ne prouve pas la production.
Aucun nouvel exercice complet de restauration ou panne PostgreSQL n'est revendiqué.

Prochain incrément recommandé : COM-04, agenda manuel, après décision AMEN INVEST
sur participants, visibilité, fuseau et annulation. Les questions métier restent
dans `open-questions.md` ; aucune restructuration de services n'est proposée.
