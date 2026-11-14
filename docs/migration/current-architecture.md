# Audit de l'architecture actuelle

**Current status ? S4, 2026-11-14:** Data Integration is independently running and active on the local synthetic deployment, with its own restricted PostgreSQL schema. All 38 public routes remain compatible. Forward cutover, post-write rollback, restore and independent process restart were verified. IAM, Client/CRM and Commercial are not yet independently extracted. Docker/production deployment remains unverified. See [S4 results and operations](s4-cutover.md) and [verified ownership inventory](s4-inventory.json). Earlier status statements below are historical.

> Nouvelle decision utilisateur apres M2 : cible a quatre services larges sur une instance/base PostgreSQL, schemas et credentials separes. Prospects et interactions appartiennent a Client & CRM. Le [plan de decomposition courant](coarse-services-plan.md) remplace les anciennes recommandations de ce document ; les preuves historiques M1/M2 restent conservees.


Audit du 14 novembre 2026. **Constats du code et du catalogue PostgreSQL local**, distincts de la cible proposée. Cette intervention est documentaire : aucune extraction, migration appliquée, réinitialisation, modification de données métier ou modification du frontend.

La demande utilisateur d'architecture par services déployables indépendamment remplace la décision monolithe d'`AGENTS.md` et des anciens documents. Le numéro « Phase 4 » ne prouve pas l'achèvement des fonctionnalités prévues dans l'ancien backlog : l'inventaire ci-dessous fait foi pour cette analyse.

## Déploiement et structure constatés

| Élément | Implémentation et preuve |
|---|---|
| Backend | Un projet Django, `backend/config/settings.py`, un URLConf `config/urls.py`, un WSGI, une connexion PostgreSQL `default`. Django 5.2.19, DRF 3.18.3, drf-spectacular 0.30.0 et psycopg 3.2.12 dans le verrou Python. Aucun FastAPI. |
| Modules réels | `identity`, `clients`, `ingestion`, `audit`, `core`. Aucun app commercial séparé : Prospect, Interaction et Opportunity sont dans `clients`. Aucun app reconciliation, reporting ou IA. |
| Frontend | React/TypeScript/Vite/Tailwind, Router, Query, RHF/Zod et Recharts. `frontend/src/app/App.tsx` et clients HTTP same-origin. |
| Infrastructure | `compose.yaml` : `db` PostgreSQL 17-alpine avec volume persistant, un `backend`, un `frontend`. PostgreSQL non publié ; ports applicatifs liés à 127.0.0.1. Aucun API Gateway de production. |
| Images | Dockerfiles non-root ; Django `runserver` et Vite `npm run dev`. Configuration de développement, pas de serveur applicatif/proxy TLS de production, ni image indépendante par domaine. Migrations lancées explicitement, pas au démarrage automatique. |
| Données | Une base, schéma public, FK inter-apps, transactions et verrous communs. UUID internes indépendants des identifiants source. Pas de cloisonnement des credentials par service. |

L'audit porte sur le code applicatif, les migrations, les configurations, les scripts et les tests du dépôt ; dépendances vendoriées, caches, binaires, références privées et données client ne sont pas recopiés dans ces documents. Les PDF et classeurs ne nécessitent aucune nouvelle extraction de contenu personnel pour analyser les frontières logicielles.

## Fonctionnalités réellement présentes

| Domaine | Code inspecté | État constaté |
|---|---|---|
| Identité / sécurité | `identity/models.py`, `policies.py`, `authentication.py`, `services.py`, `views.py` ; `core/*` | Sessions Django, CSRF, budget de connexion PostgreSQL, capacités explicites, rôles, memberships, scope assigned/organization, expiration/révocation, délégation limitée et audit. |
| Clients | `clients/models.py`, `views.py`, `serializers.py`, `services.py`, `workspace.py`, `workspace_views.py` | Panorama filtré/paginé ; clients AICED manuels ; sous-types physique/moral ; Client 360, profils CRM éditables ; identités source et comptes en lecture seule. |
| Commerce | `clients/prospects.py`, `workspace.save_activity`, modèles et tests associés | Création/qualification des prospects, prochaine action indicative, interactions réalisées, opportunités/estimations TND Decimal(18,3), version optimiste. Ni agenda/rappels, ni campagnes, ni conversion automatique. |
| Intégration | `ingestion/parser.py`, `templates.py`, `models.py`, `services.py`, `views.py` | XLSX via openpyxl : trois modèles positionnels (33/25/41 colonnes), staging, ISO/DMY explicite, contrôles fichier/lignes/doublons, prévisualisation, CSV de rejets, règles à deux acteurs et publication de snapshots immuables. |
| Source automatique | `ingestion/sources.py` | Contrat `ReadOnlySource` et fixture `SyntheticReadOnlySource`. `CarthagoReadOnlySource.read()` lève NotImplementedError. `ManualExcelSource` est aussi un stub : l'import manuel fonctionne par parser/services HTTP, **pas par cet adaptateur**. Pas de synchronisation automatique ou d'ordonnanceur. |
| Rapprochement | Aucun modèle, migration ou endpoint | Non implémenté. Publier un import ne crée ni lien Party ni compte, ne rapproche ni ne remplace les données source. |
| Reporting / IA | Dashboard React et aperçu DEV ; aucun service backend dédié | Compteur clients via API ; métriques non définies indisponibles, exemples de maquette explicitement fictifs. Aucun moteur KPI, scoring, rapport métier ou IA opérationnel. |
| Audit | `audit/models.py`, `services.py`, `views.py`, migrations ; `core/errors.py` | Audit durable de mutations et sécurité, trigger append-only, contexte minimal, lecture bornée par organisation. Historique de lot lu directement depuis AuditEvent dans `ingestion/views.BatchView`. |

## Modèle et migrations

21 modèles applicatifs : Identity (7), Clients/Commerce (9), Ingestion (4), Audit (1), plus tables Django auth/contenttypes/sessions et associations M2M. [L'inventaire de propriété](database-ownership.md) recense chaque table et chaque relation traversant les frontières proposées.

Lecture du catalogue local dans une transaction explicitement `READ ONLY` : **16 migrations applicatives appliquées**, Identity 0001–0002, Clients 0001–0006, Ingestion 0001–0005, Audit 0001–0003. Ce constat concerne uniquement l'environnement local inspecté, pas une base de production. Les métadonnées FK ont été comparées aux modèles et aux migrations SQL ; aucune donnée client n'a été extraite.

Contraintes à préserver : unicités des identifiants source ; affectation Party/Membership de même organisation par FK composite ; sous-type Party exactement cohérent par triggers différés ; impossibilité de réaffecter la PK d'un sous-type ; notes CRM ≤ 5 000 caractères ; statuts/devises/montants contrôlés ; séparation créateur/approbateur et déposant/publieur ; clé complète d'idempotence des imports ; triggers interdisant UPDATE/DELETE du staging, des snapshots et de l'audit. Les FK métier utilisent PROTECT ; ne pas les remplacer par des suppressions distantes en cascade.

`FinancialAccount` n'est qu'une projection source minimale (source, external_id, source_as_of, product_label), sans solde ni position. Elle n'a **aucune FK vers SourceSnapshot/ImportBatch**. Le snapshot versionné ne constitue pas un référentiel financier complet ou un mapping approuvé.

## Authentification, autorisation et atomicité

- `SessionAuthentication`, cookie HttpOnly/SameSite=Lax, CSRF pour mutations et connexion ; cookie Secure/redirect HTTPS hors DEBUG. Aucun JWT navigateur ou credential localStorage. `/api/auth/access/` ne décrit que les grants du demandeur.
- `grants()` relit les états actifs et expirations en base. `client_queryset()` joint les rôles/memberships avec Party **et Prospect** ; Identity importe donc Clients, qui importe Identity. Les droits financiers, lecture client et capacités métier sont intersectés **sur le même objet/organisation** ; les scopes ne s'héritent pas aux organisations enfants.
- Refus par défaut ; staff/superuser/groupes Django n'accordent pas d'accès métier. Les listes sont limitées avant compteur/pagination. Les prospects sont exclus du répertoire clients et nécessitent prospects.view sur toutes les voies historiques et workspace.
- Les mutations IAM, CRM, prospects, activités et publication import verrouillent la **même ligne Organization** et revérifient les droits après attente. Le test `RevocationRaceTests` exige qu'une écriture CRM en attente échoue après une révocation concurrente.
- AuditEvent est écrit dans la transaction de mutation : son échec annule l'écriture. `login_session()` persiste aussi la session dans cette transaction. Un simple appel HTTP d'audit ou de permissions ne remplace pas ces garanties.
- BoundedJSONParser, StrictSerializer, enveloppe `{error:{status,details}}`, identifiant de requête et `Cache-Control: no-store` sont transversaux. La rotation CSRF après login et les statuts actuels (notamment 403 de session absente) font partie du contrat React.

## Inventaire des routes publiques actuelles

Préfixe `/api/`, UUID inchangés. Cette table complète `backend/config/urls.py` ; méthodes métier indiquées, hors OPTIONS/HEAD gérés par les vues.

| Routes | Méthodes | Propriétaire cible |
|---|---|---|
| `health/` ; `schema/` | GET ; santé minimale publique, schéma authentifié | Gateway pour routage/contrat composé ; santé interne par service |
| `session/`, `auth/csrf/`, `auth/access/` | GET | Identity & Access |
| `auth/login/`, `auth/logout/` | POST | Identity & Access |
| `organizations/{org}/users/` | GET, POST | Identity & Access |
| `organizations/{org}/memberships/{id}/` | PATCH | Identity & Access |
| `organizations/{org}/role-assignments/` ; `…/role-assignments/{id}/` | GET, POST ; DELETE | Identity & Access |
| `organizations/{org}/roles/` | GET | Identity & Access |
| `audit/` | GET | Façade d'audit Identity & Access, portée inchangée |
| `clients/`, `clients/context/`, `clients/{party}/`, `clients/{party}/workspace/` | GET | Client |
| `clients/create/` | POST | Client |
| `clients/{party}/identity/`, `…/profile/`, `…/crm/` | PATCH | Client (crm = compatibilité notes seules) |
| `clients/{party}/accounts/` | GET exclusivement | Client |
| `clients/{party}/interactions/`, `…/opportunities/` | GET, POST | Commercial, malgré le préfixe clients |
| `clients/{party}/interactions/{activity}/`, `…/opportunities/{activity}/` | GET, PATCH | Commercial |
| `prospects/` ; `prospects/context/` ; `prospects/{party}/` | GET/POST ; GET ; GET/PATCH | Commercial, composition avec Client/IAM |
| `imports/context/` | GET | Data Integration |
| `imports/{org}/batches/` ; `…/upload/` | GET ; POST binaire | Data Integration |
| `imports/{org}/batches/{batch}/` ; `…/rejections/` ; `…/publish/` | GET ; GET CSV ; POST | Data Integration |
| `imports/{org}/policies/` ; `…/policies/{policy}/approve/` ; `…/revoke/` | GET/POST ; POST ; POST | Data Integration |

## Contrats et dépendances React

Routes à conserver : `/connexion`, `/tableau-de-bord`, `/clients`, `/clients/:id`, `/prospects`, `/gestion-donnees`, redirections et paramètres de recherche/onglet/aperçu. AppShell, design tokens et écrans restent identiques.

`lib/api.ts` utilise fetch same-origin, cookie de session, renouvellement CSRF avant mutation, types OpenAPI. `lib/workspace-api.ts` valide Workspace avec Zod et appelle séparément comptes/interactions/opportunités/imports. `ProspectsPage.tsx` contient aussi des appels directs et son schéma Zod : modifier uniquement api.ts ne suffirait pas en cas de changement de contrat. Le tableau de bord lit le compteur de `GET clients/`, pas un Reporting Service.

Workspace assemble Party, sous-type, CRM, manager, permissions, indicateur is_prospect et dernière situation de compte autorisée. **Il ne renvoie pas les listes d'activités**, déjà chargées séparément par React. Cela permet de conserver son JSON dans Client sans transformer le Gateway en moteur métier ; le discriminateur prospect devra devenir une donnée du registre Client avant extraction Commercial.

AuthProvider rafraîchit les grants toutes les 30 s et au focus, nettoie les caches à la déconnexion. Ce rafraîchissement d'affichage n'est pas une garantie de sécurité : les contrôles serveur actuels sont immédiats. Pagination/compteurs, chaînes Decimal, dates, booléens de permissions, 200/201 de replay d'upload, 204 logout, téléchargement CSV et erreurs 409/413/429 doivent rester compatibles. Plusieurs schémas OpenAPI sont génériques OBJECT ; compléter les tests de contrat avant de les utiliser comme preuve exhaustive.

## Tests et vérifications de cet audit

Inventaire statique : **90 méthodes de test backend** (Identity 60, Core 6, Workspace 4, Prospects 6, Ingestion 14), 12 scénarios Playwright déclarés dont un réservé au build compilé. Pas de suite audit séparée : beaucoup de tests audit/clients/sécurité résident dans `identity/tests.py`. Les suites Workspace/Prospects/Ingestion réutilisent ses fixtures ; elles ne sont pas isolées par service. PostgreSQL est indispensable aux tests de triggers et concurrence ; SQLite les ignore.

Historique contrôlé : `docs/prospects-mvp-status.md` rapporte 90 tests PostgreSQL réussis ; les rapports locaux datés du 14 novembre contiennent 11 succès Chromium DEV et 6 succès sur le bundle compilé, sans échec. **Ces suites n'ont pas été réexécutées pour cet audit documentaire.** Le runner navigateur écrit des fixtures/activités/imports dans la base locale ; ne pas le lancer contre des enregistrements à préserver.

Vérifications exécutées maintenant : inventaire AST des modèles/migrations/tests, lecture PostgreSQL des métadonnées, `check` OK, `makemigrations --check --dry-run` sans changement, `spectacular --validate --fail-on-warn` OK (artefact privé `.local/migration-audit-schema.yaml`). Aucune migration ni commande seed/test de données exécutée. Aucun déploiement Docker, restauration ou architecture distribuée testé ; les contrôles futurs sont des critères du plan, pas des résultats acquis.

Contrôle final : empreintes de 117 fichiers applicatifs/configuration/scripts/migrations identiques avant/après, aucun ajout/suppression dans ce périmètre ; six livrables présents, liens locaux et fences Markdown contrôlés. Catalogue PostgreSQL : FK composite same-org et les huit triggers métier d'intégrité/immuabilité présents. Les seuls changements livrés sont les six documents et les mises à jour architecture/roadmap/questions ; l'artefact OpenAPI de contrôle reste privé sous `.local/`.
