# Docker Compose — organisation et commandes courantes

La cible reste quatre services Django, Nginx, React et PostgreSQL. S8 renomme les
configurations par usage, sans changer les ports, credentials, schémas, startup
dependencies ou health checks de la stack acceptée. Aucun fichier de production
n'est créé : serveurs de développement/preview, DEBUG et entrée HTTP restent des
limites locales documentées dans le bilan S7.

## Structure et conservation historique

| Ancien nom | Nom courant | Usage et combinaison |
|---|---|---|
| `compose.s7.yaml` | `compose.yaml` | Stack principale quatre services, application compilée, port 5187 |
| `compose.s7.dev.yaml` | `compose.dev.yaml` | Override frontend Vite développement sur la stack principale, aucune base supplémentaire |
| Nouveau, isolation nécessaire aux tests S8 | `compose.test.yaml` | Override projet `aiced-test`, secrets propres, port 5188, volume dédié ; avec la stack principale |
| Ancien `compose.yaml` | `compose.legacy.yaml` | Base historique monolithique, réservée aux procédures de migration/reprise antérieures |
| `compose.s3.yaml` | `compose.integration-candidate.yaml` | Candidat Integration sur restauration contrôlée, profils historiques `s3`/`s3-tools` conservés ; avec legacy |
| `compose.s4.yaml` | `compose.integration-cutover.yaml` | Bascule Integration historique ; avec legacy uniquement |
| `compose.s5.yaml` | `compose.iam-cutover.yaml` | Bascule IAM avec Integration, inclut les dépendances S5 ; avec legacy, sans overlay Integration |
| `compose.s6.yaml` | `compose.commercial-cutover.yaml` | Bascule Commercial avec IAM/Integration ; avec legacy, sans empiler les anciens overlays |
| `compose.direct.yaml` | `compose.legacy-direct.yaml` | Ancien retour par ports directs ; avec legacy uniquement après arrêt coordonné du Gateway |

Ces fichiers historiques ne sont pas des doublons supprimables : les documents
S3–S6b les utilisent pour les répétitions, migrations et reprises après écritures.
Ils ne doivent jamais être empilés sur le nouveau `compose.yaml`, ni utilisés
pour réactiver le monolithe sur les données canoniques courantes. Aucune reprise
de propriété n'est autorisée ou exécutée par S8.

Les commandes opérationnelles des documents sont mises à jour ; leurs en-têtes
signalent ce renommage. Les inventaires/manifests JSON capturés et le README
historique conservent leurs anciens noms pour ne pas réécrire les preuves.
Consulter cette table pour interpréter ces références historiques.

Autres noms clarifiés : `backend/Dockerfile.s7` → `Dockerfile.acceptance`,
`frontend/Dockerfile.s7` → `Dockerfile.compiled`, `vite.s7.config.ts` →
`vite.compose.config.ts`, `infra/s7/` → `infra/acceptance/`, scripts `s7_prepare`,
`s7_browser`, `s7_inventory`, `s7_recovery`, `s7_backup` → `compose_*` correspondants.
`.env.example` devient `.env.legacy.example` ; ce template n'est pas utilisé par
la stack courante. Les Dockerfiles IAM/Commercial/Integration et les Dockerfiles
historiques par défaut sont conservés car référencés par les overlays.

Les noms internes `aiced-s7`, `aiced-s7-python`, le volume
`aiced-s7_s7_database`, `.local/s7/`, le nom interne de base et `/s7` dans le job
sont intentionnellement conservés. Les renommer aurait changé l'identité de
déploiement ou nécessité de déplacer des données/secrets. Le test de parité
compare les configurations anciennes et nouvelles avec Docker Compose, en
autorisant uniquement les changements de chemins/noms documentés.
La référence `infra/acceptance/compose-layout-baseline.json` est figée depuis les
sources Git antérieures au renommage, sans interpolation ni résolution des env
files et avec chemins portables. Elle ne contient aucun secret et permet de
refaire la comparaison après un nouveau commit.

## Application et développement

Prérequis : Docker Engine et Compose 2.24.4+ (`!override` pour les tests), Python.

```powershell
python scripts/compose_prepare.py   # première installation seulement
docker compose up --build -d --wait --wait-timeout 180
docker compose ps --all
```

<http://127.0.0.1:5187>. Une configuration privée existante est conservée ; le
générateur refuse d'écraser les secrets. Le job d'initialisation refuse une base
partiellement initialisée et ne reseed pas une base déjà initialisée. Il ne se
substitue pas à une procédure de migration production. Les quatre services
runtime ne possèdent pas le compte admin/migrateur ; PostgreSQL n'a pas de port
publié. Carthago ne reçoit aucun appel ni écriture.

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait
docker compose restart gateway
# Revenir au frontend compilé :
docker compose up --build -d --wait
docker compose restart gateway
```

Un redémarrage Gateway est nécessaire après recréation de conteneurs dont les IP
ont changé ; ce comportement Nginx est conservé. Le mode dev partage volontairement
la base de l'application locale ; les tests automatisés utilisent le projet isolé
ci-dessous. `docker compose stop` conserve les données. Ne pas utiliser `down -v`
pour basculer de mode, migrer ou revenir en arrière.

## Test isolé

Le projet `aiced-test` utilise `.local/compose-test/`, des passwords/clés/certificats
générés indépendamment et le volume explicite `aiced-compose-test-database`.
Même nom interne de base mais **autre cluster PostgreSQL, réseau, volume et secrets**.
Le test ne peut pas monter le volume principal via l'override fourni. Ne pas
remplacer ces valeurs ni le nom de projet avec `-p` ou des variables ad hoc.
Il n'existe aucune connexion à la base portable de développement ou de production.

```powershell
python scripts/compose_prepare.py --test
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
python scripts/compose_validate.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/history.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/imports.py
python scripts/compose_browser.py --test
python scripts/compose_history_restart.py --test
python scripts/compose_inventory.py --test
```

<http://127.0.0.1:5188>. Les sondes de révocation et de panne modifient temporairement
des permissions/disponibilités synthétiques : les exécuter **avant** les tests
navigateur, pas en parallèle. Les régressions Django utilisent une troisième
base temporaire, interne au cluster test, avec fixtures exclusivement synthétiques.

Le navigateur tourne sur l'hôte contre Nginx Docker ; aucun serveur local n'est
lancé. Prérequis : Node 22+, dépendances `frontend/package-lock.json`, Chromium
Playwright et Python/openpyxl (`backend/requirements.lock`, ou outils privés
existants dans `.tools`). Le runner accepte `AICED_NODE_BINARY` ou Node du PATH.
Exemple d'installation navigateur : `npm --prefix frontend ci`, puis dans
`frontend`, `npx playwright install chromium`.

```powershell
# Suite mode développement dans le même environnement test isolé :
docker compose -f compose.yaml -f compose.test.yaml -f compose.dev.yaml up -d --no-deps --wait frontend
docker compose -f compose.yaml -f compose.test.yaml restart gateway
python scripts/compose_browser.py --test --development
# Restaurer le build compilé :
docker compose -f compose.yaml -f compose.test.yaml up -d --no-deps --wait frontend
docker compose -f compose.yaml -f compose.test.yaml restart gateway
```

Les tests spécifiques à un mode sont explicitement ignorés dans l'autre mode.
Le schéma OpenAPI gelé est lu depuis l'artefact privé M1, copié lors de la
préparation ; s'il est absent, fournir la référence revue dans
`.local/compose-test/openapi-baseline.yaml`. Ne jamais générer l'attendu depuis
le candidat. Les 38 routes historiques restent gelées ; les additions explicites
S8 sont vérifiées séparément par `backend/contracts/additions.py`.

Pour rejouer les pannes et une sauvegarde/restauration dans ce cluster jetable :
`python scripts/compose_recovery.py --test`. Le runner refuse un restore target
existant ; ne jamais l'orienter vers une base réelle. Les procédures historiques
de rollback nécessitent leurs propres gates et ne sont pas exécutées ici.

Rapports privés : `.local/compose-test/*-report.json`, `*-tests.log` et rapports
navigateur ; inventaire de nommage `.local/s8/compose-validation.json`.
Aucun fichier CI/CD n'existe dans ce dépôt à mettre à jour.

## Ajout fonctionnel S12 — migrations de l'agenda

Les fichiers Compose restent inchangés. L'initialiseur appelle désormais
`infra/acceptance/agenda_migrate.py` avant les services, y compris sur une base
synthétique déjà initialisée. Il applique la nouvelle branche Client et ses FK
locales puis attribue atomiquement SELECT/INSERT/UPDATE au seul runtime Client,
sans DELETE, réensemencement ni transfert d'ownership. Le script refuse une
base sans le marqueur synthétique attendu ; ce n'est pas une procédure de
migration production.

Le fuseau par défaut est `Africa/Tunis`. `AICED_AGENDA_TIME_ZONE` peut être fourni
dans l'environnement privé Client après validation métier et revue d'impact
sur les instants existants ; aucune variable secrète n'est ajoutée au dépôt.

Après les suites navigateur, exécuter séquentiellement :

```powershell
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/agenda.py
python scripts/compose_agenda_restart.py --test
```

Voir [la recette S12](migration/s12-manual-agenda.md). Les preuves S7/S8 de
sauvegarde/restauration demeurent historiques, distinctes de ces nouveaux contrôles.

## Validation de volume S13

Aucun fichier Compose, port, volume ou credential n'est modifié en S13. Le
benchmark `infra/acceptance/pipeline_scale.py` et la recette
`pipeline_scale_verify.py` sont réservés au projet test et à sa base marquée
synthétique. Ils conservent les références immuables de leurs données de test.
Ne pas les lancer pendant les suites navigateur, les mesures ou les pannes.

Les commandes exactes, métriques avant/après et limites de capacité sont dans
[la recette S13](migration/s13-pipeline-scalability.md). Le test navigateur de
volume est activé par `AICED_E2E_SCALE=1` après création du jeu de 10 000 ; sans
cette variable, il est explicitement ignoré et ne constitue aucune preuve de
capacité. La reprise pipeline inclut désormais une vraie coupure PostgreSQL.

## Migration et recette S14

Compose, ports, volumes et secrets inchangés. Initialize applique explicitement
`commercial_store/0003_campaign_draft.py` via `infra/acceptance/campaign_migrate.py`,
avant les services : propriétaire Commercial existant, table privée et seuls
SELECT/INSERT/UPDATE au runtime Commercial. Procédure réservée à la base jetable
marquée synthétique. Après build et redémarrage gateway :

```powershell
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/campaigns.py
python scripts/compose_browser.py --test campaigns.spec.ts
python scripts/compose_campaign_restart.py --test
```

`/campagnes` prépare seulement des brouillons personnels.
`AICED_COMMERCIAL_TIME_ZONE` est facultatif dans l'environnement privé Commercial,
Africa/Tunis par défaut. Voir la [recette S14](migration/s14-manual-campaigns.md)
pour les garanties, résultats et décisions restantes ; aucune readiness production.
