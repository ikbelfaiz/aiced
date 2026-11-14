# AICED

> Current architecture: **S6b verified locally**. IAM, Client & CRM, Commercial and Data Integration run separately with restricted data ownership. All 38 routes are preserved; actual post-write rollback/forward, browser workflows and restore were verified. See [S6b report](docs/migration/s6b-commercial.md). Container execution and production readiness remain unverified. Earlier phase status paragraphs below are historical.


**Current status: S5 (2026-11-14).** IAM and Data Integration are independently running in the local synthetic deployment with separate restricted schemas/credentials. All 38 public routes are preserved. Post-write rollback, forward cutover, restore and independent IAM restart were verified. Client/CRM and Commercial remain in the compatibility backend. See [S5 results, startup and rollback](docs/migration/s5-iam.md) and [actual ownership](docs/migration/s5-inventory.json). Docker and production deployment are not verified. Earlier status statements below are historical.

S2 : [contrats internes, garanties de révocation, audit/outbox, migrations et prérequis Integration](docs/migration/s2-authorization-audit.md). Les 38 routes publiques restent inchangées ; aucun service métier extrait. Appliquer les deux migrations additives avant le nouveau code ; pour le cluster portable local, `python scripts/s2_migrate_local.py --confirm-local-additive` vérifie d'abord une sauvegarde/restauration et une migration scratch.

**Direction actualisee : quatre services Django/DRF larges (IAM, Client & CRM, Commercial, Integration), schemas/credentials separes sur PostgreSQL partage.** Voir [le plan courant et S1](docs/migration/coarse-services-plan.md). Le monolithe actuel est transitoire ; les anciennes recommandations M2 de le conserver comme cible finale sont remplacees. Aucun service metier independant encore livre dans S1.

Premier incrément de migration M1 : `python scripts/migration_baseline.py --confirm-synthetic` crée deux bases locales temporaires, vérifie sauvegarde/restauration et contrats, puis exécute les tests backend/navigateur sur les données synthétiques isolées. La base applicative existante reste en lecture seule et ses empreintes avant/après sont comparées. Les artefacts privés restent dans `.local/migration-baseline/`. Aucun service métier extrait ni changement de propriété de données ; Gateway M2 implemente : voir [configuration, tests et rollback](docs/migration/m2-gateway.md). Voir [le bilan et le rollback M1](docs/migration/m1-baseline-status.md).

MVP commercial autonome : `/prospects` permet la création/qualification AICED puis les interactions et opportunités sur la fiche partagée. `python manage.py seed_prospects --confirm-synthetic`, après les seeds existants et uniquement en DEBUG, ajoute deux prospects synthétiques et un rôle prospects séparé à `synthetic.operator.a`. Aucun rôle Phase 1 élargi. Les snapshots source restent isolés et immuables, sans écriture Carthago. Voir [le bilan de cette tranche](docs/prospects-mvp-status.md).

CRM AMEN INVEST : sessions, rôles/périmètres, audit, Connexion, Tableau de bord, Panorama Clients, Client 360° et Gestion des données. Import Excel manuel avec staging et publication de snapshots immuables ; aucune mise à jour de client/compte source ni intégration Carthago automatique. Voir [l'architecture](docs/architecture.md), le [modèle de sécurité](docs/security-model.md) et le [bilan Client 360 / Data Management](docs/client-360-data-management-status.md).

## Prérequis et démarrage local

Docker Engine avec Compose v2. Pour travailler sans conteneurs : Python 3.12, PostgreSQL 17, Node 22.12+ et npm.

1. Copier `.env.example` vers `.env` et remplacer les secrets Django, PostgreSQL et Gateway. Générer une clé indépendante avec `python -c "import secrets; print(secrets.token_urlsafe(50))"`. Ne jamais versionner `.env`.
2. `docker compose build`
3. `docker compose up -d db`
4. `docker compose run --rm backend python manage.py migrate`
5. `docker compose up -d backend frontend gateway`
6. Ouvrir http://localhost:5173 ; vie API : http://localhost:5173/api/health/. Le Gateway est le seul port applicatif publié par défaut ; renseigner aussi `AICED_GATEWAY_KEY` dans `.env`.

Le statut de vie ne valide pas la disponibilité PostgreSQL. `/api/session/` et `/api/schema/` nécessitent une session authentifiée. Pour produire OpenAPI hors ligne : `docker compose run --rm backend python manage.py spectacular --file /tmp/schema.yaml --validate`.

## Authentification et API

1. `GET /api/auth/csrf/` : conserver le cookie et le `csrfToken` retourné.
2. `POST /api/auth/login/` avec JSON `username`, `password` et en-tête `X-CSRFToken` ; conserver le cookie de session.
3. Relire `/api/auth/csrf/` après connexion : le jeton a tourné. Chaque mutation authentifiée exige ce nouveau jeton.
4. `GET /api/auth/access/` donne uniquement les grants actifs de l'utilisateur et leurs identifiants d'organisation.
5. `POST /api/auth/logout/` avec CSRF invalide la session serveur.

API Phase 1 : `/api/clients/`, `/api/clients/{uuid}/`, `PATCH /api/clients/{uuid}/crm/` (notes uniquement), `/api/clients/{uuid}/accounts/` (lecture seule), `/api/audit/`, et `/api/organizations/{uuid}/users/`, `memberships/{uuid}/`, `roles/`, `role-assignments/`. Le détail des méthodes et champs est dans OpenAPI. Listes paginées (50 éléments). Les query params ne permettent pas d'élargir un périmètre. Pas d'API de modification des définitions de rôles, de mot de passe d'un compte existant ou de flags superuser.

Les mutations acceptent uniquement `application/json`. `API_MAX_JSON_BYTES` fixe la limite du corps JSON (65 536 octets par défaut), avec erreur JSON 413 en cas de dépassement. Les notes sont limitées à 5 000 caractères par validation de service et contrainte SQL. Les réponses d'authentification, d'accès et de modification CRM sont décrites par des serializers explicites dans OpenAPI.

## Données synthétiques facultatives

Le seed exige `DJANGO_DEBUG=1`, `--confirm-synthetic` et un mot de passe conforme dans `AICED_SEED_PASSWORD` (le transmettre via environnement, pas en argument shell). Dans un shell local où ces variables sont exportées :

```sh
python backend/manage.py seed_synthetic --confirm-synthetic
```

Avec Compose : exporter `AICED_SEED_PASSWORD` dans le shell hôte puis `docker compose run --rm -e AICED_SEED_PASSWORD backend python manage.py seed_synthetic --confirm-synthetic`.

Crée 2 organisations, 6 utilisateurs `synthetic.{reader,manager,it}.{a,b}`, 2 clients et 2 comptes locaux marqués `SYNTHETIC_ONLY`, sans encours. Aucun mot de passe existant remplacé lors d'un replay. Reader : clients affectés et notes ; manager : organisation, finance locale, habilitations et audit ; IT : habilitations seules, sans accès clients/finance. Ces rôles de démonstration ne valent pas validation des rôles métier de production.

## Vérifications

```sh
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend python manage.py test core identity clients ingestion audit
docker compose run --rm frontend npm run build
```

Le test runner PostgreSQL doit pouvoir créer sa base de test en développement. Ne jamais exécuter ces commandes contre une base production.

Sans Docker : créer un venv, installer `backend/requirements.lock`, exporter les variables de `.env` dans le shell (Django ne charge pas ce fichier automatiquement), définir `POSTGRES_HOST=127.0.0.1`, puis exécuter `python backend/manage.py migrate` et `python backend/manage.py runserver`. Dans frontend : `npm ci`, puis `npm run dev`. Vite relaie `/api` pour garder une seule origine.

Tests unitaires isolés uniquement : `python backend/manage.py test core identity clients ingestion audit --settings=config.test_settings`. Les tests de contraintes/concurrence spécifiques PostgreSQL y sont ignorés ; SQLite ne remplace donc pas la suite PostgreSQL. `config.test_settings` ne doit jamais servir au démarrage d'une application.

Dans l'environnement de vérification Windows préparé ici, un cluster privé est sous `.local/postgres`, sur `127.0.0.1:55432`. `python scripts/backend_check.py migrate` et `python scripts/backend_check.py test core identity clients ingestion audit` chargent son environnement privé sans afficher les secrets. Le mot de passe synthétique généré pendant la vérification est dans `.local/postgres/seed-password` ; aucun secret n'est versionné. `scripts/local_postgres.py` peut redémarrer ce cluster en conservant les secrets ; il dépend des binaires PostgreSQL locaux dans `.tools/` et ne remplace pas le setup Compose standard. Pour l'arrêter : `.tools/pgsql/bin/pg_ctl.exe -D .local/postgres/data -m fast -w stop` (aucune donnée supprimée).

`python scripts/smoke_proxy.py` vérifie le parcours HTTP réel Vite → Django (santé, session, Origin/CSRF, lecture filtrée et déconnexion) avec ce seed et les outils locaux. Il lance puis arrête ses propres serveurs sur des ports temporaires ; il ne modifie pas les dossiers clients. Le bilan courant de revue est dans [phase-1-review.md](docs/phase-1-review.md).

## Écrans frontend

La phase suivante ajoute `/clients/:id` et `/gestion-donnees`. Les clients AICED, profils CRM, interactions et opportunités peuvent être créés/modifiés selon habilitation ; les attributs source et comptes restent en lecture seule. Publication Excel limitée aux snapshots immuables sous règle revue, jamais à une fusion CRM implicite. Schémas et frontières : [import-templates.md](docs/import-templates.md).

Le seed séparé `python manage.py seed_workspace --confirm-synthetic` (DEBUG=1, `AICED_SEED_PASSWORD` privé) prépare `synthetic.operator.a` et `synthetic.reviewer.a` dans l'organisation synthétique A. Il ne modifie pas les rôles Phase 1 existants. Operator crée/édite le CRM, dépose les fichiers et propose les règles ; Reviewer approuve les règles et publie les lots d'un autre acteur. Ces comptes et approbations de test ne sont pas une matrice métier production.

`/connexion`, `/tableau-de-bord` et `/clients` utilisent les sessions et API existantes. Les autres modules sont indiqués indisponibles. Aucune intégration Carthago. En développement uniquement, un utilisateur disposant des permissions clients et finance peut ouvrir l'aperçu fictif de référence via le lien « Aperçu maquette » ; les données API restent le mode normal.

Après `npm ci` dans frontend et installation Chromium (`npx playwright install chromium`), `python scripts/frontend_e2e.py` utilise l'environnement privé Windows décrit ci-dessus pour les tests navigateur. Les vérifications standard backend restent `python manage.py test core identity clients ingestion audit` depuis backend. Détails : [bilan frontend](docs/frontend-phase-status.md), [références et écarts](docs/frontend-design-system.md).

## Données et dépendances

`references/`, `.local/` et `.tools/` sont privés et ignorés. Le script d'inspection requiert PyMuPDF et openpyxl, uniquement pour la revue locale. Il écrit des extractions privées sous `.local/`, sans copier de données client vers le code. Seuls les exemples fictifs de la maquette sont transcrits pour l'aperçu visuel de développement. Les références ne sont pas nécessaires au runtime.

`backend/requirements.txt` exprime les contraintes ; `backend/requirements.lock` fixe le toolchain Python vérifié. Le verrou npm fixe les dépendances frontend. Une revue de vulnérabilités, la séparation des rôles PostgreSQL migration/runtime et le verrouillage des images par digest restent nécessaires avant préproduction ; les images locales ne sont pas déclarées reproductibles bit à bit. Le [bilan Phase 0](docs/phase-0-status.md) reste historique.
