# AICED — décomposition en services larges et première tranche S1

**Current status ? S4, 2026-11-14:** Data Integration is independently running and active on the local synthetic deployment, with its own restricted PostgreSQL schema. All 38 public routes remain compatible. Forward cutover, post-write rollback, restore and independent process restart were verified. IAM, Client/CRM and Commercial are not yet independently extracted. Docker/production deployment remains unverified. See [S4 results and operations](s4-cutover.md) and [verified ownership inventory](s4-inventory.json). Earlier status statements below are historical.

Avancement courant : **S2 implémenté**, voir [contrats, cohérence, audit, migrations et limites](s2-authorization-audit.md). Le corps S1 ci-dessous reste historique : inventaire initial de 30 tables/25 modèles/16 migrations ; l'inventaire machine est actualisé en S2 à 33 tables/28 modèles/18 migrations. Aucun service métier indépendant encore livré. La barrière S2 est globale à la base (plus conservative que la proposition par organisation ci-dessous).

## Décision qui fait foi

La dernière demande utilisateur remplace la recommandation M2 de conserver définitivement le monolithe. **Cible : quatre services Django/DRF indépendants, derrière le Nginx M2, sur une instance PostgreSQL et une base AICED comportant quatre schémas privés et des credentials distincts.** Analytics & Reporting et Audit restent des modules bornés, sans nouveau service vide. Pas de FastAPI, Kafka, Kubernetes, mesh ou serveur PostgreSQL par service.

M1/M2 et leurs preuves restent valides historiquement. Les anciens documents sont des audits datés ; leurs affectations Prospect/Interaction à Commercial et leurs quatre bases distinctes sont remplacées ici. S1 n'est pas une extraction de domaine : le runtime conserve la base publique et les routes actuelles. Aucune indépendance métier n'est déclarée.

## 1. Code réel, dépendances et responsabilités

Inspection actuelle : un projet `backend/config`, applications `identity`, `clients`, `ingestion`, `audit`, `core`, un seul `DATABASES.default`. `clients` contient à la fois CRM et opportunités ; aucun projet commercial, analytics ou reporting séparé. Compose possède déjà Nginx, Django, Vite et PostgreSQL. Aucun endpoint Carthago réel n'existe.

L'[inventaire machine](service-inventory.json), généré en lecture seule depuis Django et le catalogue PostgreSQL, recense **30 tables, 25 modèles Django enregistrés dont 21 métier, 39 FK SQL dont 13 traverseraient les nouvelles frontières, 38 routes / 47 couples méthode-chemin et 16 migrations applicatives historiques avec leurs dépendances**. Les M2M auto-créées et la FK composite same-org sont incluses dans les tables/FK. Aucune donnée client n'y figure. Les catalogues/objets système PostgreSQL ne sont pas des tables métier à transférer.

| Service cible | Code réutilisé et données | Dépendances restantes / interface future |
|---|---|---|
| Identity & Access (`iam`) | `identity/{models,authentication,policies,services,views}.py`, sessions, rôles, memberships, budgets de login ; module Audit central historique | Plus aucun import Client dans `identity/policies.py` après S1. Les utilisateurs/organisations restent la référence IAM ; principal, grants frais et résumés de membership fournis par HTTP interne. |
| Client & CRM (`client_crm`) | `clients` : Party, sous-types, CRMProfile, ExternalIdentity, FinancialAccount, **Prospect et Interaction** ; `prospects.py`, scoping dans `clients/policies.py`, services CRUD et parties CRM de workspace | Grants/résumés IAM ; l'ORM IAM subsiste jusqu'au remplacement testé. Prospect + Party + CRM + interactions restent locaux : pas de saga de création de prospect. Comptes et identités source restent read-only. |
| Commercial (`commercial`) | **Opportunity** seulement aujourd'hui ; serializers/actions/vues d'opportunité extraits de `workspace.py` / `workspace_views.py` après séparation des helpers | HTTP IAM pour utilisateur/grants, HTTP Client pour existence/org/périmètre/affectation/classification. Appointments, campagnes et workflows sont à construire ici ; pas de tables fictives. |
| Data Integration (`integration`) | `ingestion/{models,parser,templates,services,views,sources}.py` : Policy, Batch, StagingRow, SourceSnapshot | Aujourd'hui User/Organization, verrou Organization et AuditEvent. Remplacer par UUID validés, garde locale d'organisation, journal local et APIs IAM ; pas de dépendance Client pour publier un snapshot. |
| Analytics & Reporting | Aucun modèle/backend KPI aujourd'hui ; dashboard React lit le compteur Client | Premier module futur hébergé dans Commercial, uniquement quand règles KPI approuvées. Consomme des APIs filtrées, jamais des jointures libres dans les schémas voisins. |
| Audit | `audit` historique hébergé dans IAM ; journal transactionnel local dans chaque service extrait | Pas de processus central supplémentaire exigé. Livraison HTTP différée, idempotente ; la panne centrale ne doit ni perdre l'événement local ni laisser une mutation sans audit. |

Le frontend garde ses écrans, routes, requêtes relatives, cookies et schémas Zod. Le Gateway garde ses limites, erreurs, origin/Host, headers de confiance et absence de retry de mutations. Il ne devient ni moteur métier, ni autorité d'autorisation, ni utilisateur SQL.

## 2. Propriété et frontières SQL

L'annexe ci-dessous donne chaque table. L'historique `public.django_migrations` reste propriété technique du déploiement historique ; il n'est ni déplacé ni cloné comme preuve qu'un service possède ses migrations. Chaque futur schéma possède sa propre table `django_migrations`, content types nécessaires, journal et migrations propres.

AuditEvent historique et ses FK restent dans IAM. Les nouveaux journaux locaux ne portent pas de FK vers User/Organization distants : actor/org UUID vérifiés et conservés, même après désactivation. FinancialAccount appartient à Client comme projection read-only ; SourceSnapshot appartient à Integration ; **aucune fusion, FK nouvelle ou mise à jour implicite entre les deux**.

Propriétés de sécurité retenues : propriétaire de schéma NOLOGIN ; migrateur LOGIN NOINHERIT avec SET ROLE vers son seul propriétaire ; runtime LOGIN sans appartenance, sans DDL, CREATEDB, CREATEROLE, BYPASSRLS, SUPERUSER ou REPLICATION. Runtime reçoit seulement USAGE sur son schéma, CRUD sur ses tables et USAGE/SELECT des séquences ; jamais TRUNCATE ou EXECUTE implicite de nouvelles fonctions. Les tables immuables auront des droits runtime plus étroits et leurs triggers existants : les CRUD génériques du rehearsal **ne constituent pas la politique finale d'Audit/Staging/Snapshot**.

`search_path = <schéma propriétaire>, pg_catalog` sert à résoudre les noms, **pas à autoriser**. Pas de USAGE/SELECT/INSERT/UPDATE/DELETE sur les autres schémas ; pas de rôle commun applicatif. Fonctions SECURITY DEFINER, vues, extensions et permissions PUBLIC doivent être inventoriées avant cutover. Les métadonnées système ne sont pas rendues secrètes par les schémas. Les droits CONNECT hérités PUBLIC sur d'autres bases nécessitent une politique `pg_hba.conf`/cluster explicite avant production ; S1 ne révoque rien sur les autres bases et ne prétend pas isoler le cluster entier.

## 3. APIs publiques et échanges internes

Les 38 routes et leurs méthodes restent identiques (annexe exhaustive). `/api/clients/.../interactions/` et `/api/prospects/` appartiennent à Client & CRM ; seules les sous-routes `/opportunities/` sont routées à Commercial. Aucun changement d'URL React pour refléter les noms internes. `/api/health/` reste minimal ; `/api/schema/` reste authentifié avec contrat composé, initialement servi par le résidu ; ne pas transformer Nginx en générateur de schéma.

Les interfaces suivantes sont **proposées, pas encore servies**. Elles seront sur listeners/réseaux privés distincts, sans nouvelle route publique dans le manifeste M1 :

| Propriétaire | API interne versionnée proposée | Consommateurs / règles |
|---|---|---|
| IAM | `POST /internal/v1/principal/resolve` | Services : vérifier session reçue, CSRF des mutations et audience du service. Réponse minimale actor UUID/état ; cookie de session jamais enregistré dans logs/payloads d'audit. Aucun accès direct aux sessions SQL depuis Client/Commercial/Integration. |
| IAM | `POST /internal/v1/authorization/check` ; `POST /internal/v1/memberships/resolve` | Capacité(s), organisation, scope et expiration frais ; listes de références bornées. Pas d'API de dump universel de Users/grants ; jamais de rôle staff/superuser implicite. |
| Client | `POST /internal/v1/clients/authorize` | Commercial fournit party UUID + action + principal vérifiable ; Client intersecte clients.view, prospects.view si nécessaire et capacité d'action sur le même objet. Retour minimal UUID/org/classification/version ; refus 404/403 selon contrat existant. |
| Client | `POST /internal/v1/clients/query-authorized` | Recherche/filtre/pagination avant compte ; réponse minimale de références/résumés autorisés pour listes futures. Ne jamais filtrer 50 résultats après pagination. Aucun endpoint de liste Commercial n'existe encore à inventer. |
| Integration | `GET /internal/v1/snapshots/{id}` (paginé) | Futur consommateur autorisé : org, provenance, version, contenu borné. Jamais un raccourci SQL vers les comptes Client. |
| Audit hébergé IAM | `POST /internal/v1/audit/events` | Producteur authentifié, event UUID unique par producteur, digest immuable, org/acteur/action/résultat/référence/corrélation minimaux ; pas de notes ou cellules. |

HTTP synchrone avec délais bornés pour principal et autorisation, refus fermé si amont absent/invalide. Transport TLS pour communications hors hôte, secrets techniques distincts par service/audience, rotation et replay contrôlés ; pas de clé Django partagée, pas de confiance dans X-User/X-Role navigateur. La clé M2 authentifie uniquement la connexion Gateway ; **elle ne vaut pas délégation utilisateur entre services**. Un token court peut corréler une identité, mais n'est jamais la preuve de grants encore valides. Livraison audit : outbox SQL locale + worker HTTP simple avec reprise, pas de broker.

## 4. Révocation, transactions et audit

Aujourd'hui `Organization.select_for_update` sérialise IAM, CRM, commerce et publication ; les services relisent les droits après attente. Audit et mutation partagent le même commit. Ce sont des exigences de sécurité à préserver, pas du couplage à supprimer immédiatement.

Pour cette cible **une seule base PostgreSQL**, préférer tester un protocole de verrou transactionnel consultatif par organisation plutôt qu'une infrastructure distribuée d'admission : toutes les mutations IAM/Client/Commercial/Integration acquièrent le même `pg_advisory_xact_lock` dérivé de l'UUID organisation (namespace/version définis, ordre déterministe si plusieurs orgs). Le service ne lit/écrit aucune table IAM pour prendre ce verrou. Dans sa transaction locale, après acquisition, il appelle les APIs IAM et Client nécessaires, vérifie à nouveau, puis écrit son domaine + audit local. Les handlers de lecture d'autorisation IAM/Client **ne reprennent pas ce verrou**, sinon deadlock HTTP. Toutes les mutations qui changent grants, membership, organisation, affectation ou classification participent à la même barrière. Les mutations ne s'appellent pas mutuellement en conservant ce verrou.

Cela garde une sérialisation organisationnelle similaire au code actuel. Crash/timeout : rollback local, libération transactionnelle du verrou ; pas de transaction distribuée ou de connexion SQL partagée. La révocation ne commit qu'après les writes déjà admis, et un write en attente revalide après le revoke. Les collisions de clés ne doivent produire que de la contention, jamais élargir l'accès. Le protocole reste **non implémenté/non vérifié** ; vérifier attente/révocation, failover, annulation, appel HTTP bloqué, session/logout, user/org désactivés, affectation et tous les writers/jobs avant extraction. Une vérification IAM HTTP juste avant commit sans cette barrière serait insuffisante.

Si cette coordination par base est refusée à l'avenir, remplacer par admission/fencing durable vérifiée, pas par JWT périmé. Pas de cutover tant que l'équivalent de `RevocationRaceTests` n'est pas prouvé avec deux processus/credentials. Les consultations restent fraîches et filtrées avant count/pagination ; aucun cache de droits durable.

Audit : IAM garde son journal historique append-only ; chaque service extrait écrit un journal append-only dans **sa transaction métier**, plus un outbox à état de livraison séparé. Erreur locale d'audit annule la mutation. La panne de consolidation ne perd pas le journal local ; retries HTTP idempotents, event ID/digest divergents rejetés. Import history est lu localement sans attendre le central. Avant cutover, définir le contrat de fraîcheur de `/api/audit/` : si l'immédiateté est exigée, lecture fédérée filtrée avec refus d'une réponse partielle plutôt que prétendre que consolidation différée est équivalente.

## 5. Schémas, FK et migrations

Les **13 FK transfrontières réelles** sont listées en annexe. Elles deviennent des UUID immuables + références minimales validées par le propriétaire ; pas de nouvelle FK SQL entre services, même si PostgreSQL le permet. Party org/assignment : vérifier membership et org identiques via IAM et référence locale unique, conserver l'ancienne FK composite jusqu'au remplacement prouvé. Opportunity party : référence Client autorisée + org immuable ; auteur/CRM updated_by et acteurs d'import : actor UUID vérifié. Empêcher réaffectation arbitraire et disparition des références historiques ; aucune suppression distante en cascade.

Les sous-types Party, CRM, qualification Prospect et Interaction restent dans Client et gardent leurs FK locales. **Pas de saga de création de prospect** : l'ancienne proposition Commercial/Client est annulée. Opportunity + journal reste local Commercial ; publication Policy/Batch/Rows/Snapshot + journal reste locale Integration. Triggers same-org/sous-type/longueur/finance/idempotence/immutabilité sont conservés ou remplacés avec preuves explicites, jamais désactivés pour faciliter une copie.

Ne pas faire `ALTER TABLE SET SCHEMA` maintenant : il déplace une relation mais conserve des dépendances et ne résout ni ORM, ni migration graph, ni verrous, ni audit. Ne pas changer globalement search_path du monolithe ni accorder ses credentials aux nouveaux services. Conserver les 16 fichiers historiques et `public.django_migrations` intacts. Nouveaux entry points DRF avec uniquement les apps propriétaires et une lignée initiale indépendante par schéma, sans auth.User/session copiés dans chaque service. Appliquer `SET ROLE propriétaire` explicitement pour DDL ; runtime n'est jamais migrateur. Les nouvelles tables locales de référence/audit/outbox reçoivent de nouvelles migrations additives.

Avant copie/cutover : sauvegarde approuvée + restauration vérifiée, freeze du domaine, record counts par table/org et ensembles PK, empreintes privées, contraintes/FK/index/triggers/fonctions/séquences, migration dependencies, Decimal/date/NULL, versions, digests, cellules et historique exacts. Copier dans l'ordre Policy→Batch→Row→Snapshot pour Integration ; références→Party→sous-types/CRM/prospect/interactions/projections pour Client ; références→Opportunity pour Commercial ; IAM puis sessions/budgets en préservant secrets/session IDs pour auth. Pas de saves ORM altérant auto_now ou de `--fake` opportuniste.

Un seul writer : changer routes **et** jobs/ACL au cutover, retirer les droits de l'ancien writer seulement quand le remplacement est opérationnel. L'ancien code ne doit pas garder une voie SQL contournant les APIs. Le migrateur peut suspendre le domaine lors d'une migration incompatible ; ne pas promettre déploiements sans interruption ou sans coordination de version. Un cluster unique garde un domaine commun de panne/backup : choix pragmatique, pas indépendance physique totale.

## 6. Ordre, acceptation et rollback

| Lot | Travail concret et critères de passage | Retour sûr |
|---|---|---|
| **S1 — cette tranche** | Déplacer le scoping d'objets d'IAM à Client sans changement de règles ; inventaire propriétaire de 30 tables/38 routes ; rehearsal de quatre schémas/12 rôles avec connexions LOGIN réelles et refus inter-schémas. Refaire M1/M2, isolation, erreurs, concurrence et navigateurs. Zéro transfert de table, route ou ACL applicative. | Revenir aux imports/policy précédents ; aucune migration inverse. Le rehearsal supprime uniquement sa base marquée et ses rôles marqués après vérification ; la base applicative reste inchangée. |
| **S2 — autorisation/audit avant extraction** | Interface IAM interne, adaptateurs HTTP versionnés, journal local/outbox, protocole advisory après test d'équivalence. Garder le writer historique actif. Tests de faux principal/audience/replay, CSRF, grants/finance, révocation en attente, affectation, crash et panne audit. | Désactiver les adaptateurs candidats, rester avec ORM/verrous/audit actuels. Pas de service writer distant actif, conserver migrations additives. |
| **S3 — Integration candidat** | Premier service de domaine séparé, DRF + schéma/credentials propres, migrations depuis vide, parser réutilisé, fixtures synthétiques. Aucun import de modèles IAM/Client ni SELECT autorisé dans leurs schémas ; auth HTTP réelle, journaux locaux ; arrêter/redémarrer son processus sans redémarrer le résidu. Régression XLSX/idempotence/publication/revocation/HTTP. | Arrêter le candidat, Nginx continue le backend historique ; conserver preuves, aucun trafic réel ni données réelles copiées. |
| **S4 — Integration actif** | Backup/freeze/copie approuvés, parité historique et invariants, routage des 10 routes imports, ancienne voie writer neutralisée, tests navigateur et source read-only. | Avant réouverture : rerouter historique sans changement de données. Après nouveaux commits : freeze, transfert inverse exact testé des nouveaux lots/états/snapshots/journaux, parité puis un seul writer. Sinon correction en avant ; jamais restauration aveugle du vieux dump. |
| **S5 — IAM séparé** | Ses tables/sessions/budgets/journal dans schéma IAM ; remplacer tout ORM IAM dans le résidu et neutraliser les anciens credentials. Préserver mêmes cookies/CSRF/SECRET_KEY IAM. Tester login/logout, expiry, scopes et concurrence inter-processus. | Avant écriture : revenir au writer historique. Après écriture : freeze et delta de sessions/grants/audits contrôlé ; ne jamais ressusciter une révocation. Garder les barrières, sinon pas de bascule. |
| **S6 — Commercial séparé** | Opportunity seule extraite depuis Client, API publique identique, référentiel Client autorisé servi temporairement par résidu ; schéma Commercial, journal, migration propre. Tests tenant/party/activity, Decimal/version, refresh permissions et panne Client. | Writer unique et retour pré/post-commit identique ; préserver UUID et versions/opportunités/audits par delta. Sans outil inverse testé, correction en avant. |
| **S7 — résidu devient Client & CRM** | Retirer du runtime résiduel les modèles/writers IAM/Integration/Opportunity après API opérationnelle, déplacer son agrégat vers schéma Client sous freeze. Tests création atomique client/prospect, visibilité, interactions, finances read-only et dépendances. Quatre entry points/images/processus testés séparément avec leurs seuls credentials, migrations/tests isolés. | Aucune restauration globale du monolithe si domaines ont divergé. Rollback par domaine avec deltas et version compatible ; garder journaux et anciens fichiers de migration. |

Les étapes ne sont pas simultanées. S2 peut fournir la façade IAM depuis le backend historique : pas besoin d'extraire IAM en premier. L'interface Client pour Commercial reste dans le résidu jusqu'à S7. Les services autonomes ne nécessitent pas des dépôts séparés ; images/entry points/settings/URLConf/migrations/tests propres suffisent. L'audit ancien reste consultable et protégé pendant chaque étape.

## 7. Déploiements indépendants utiles et risques

**Integration** justifie le premier déploiement indépendant : parsing XLSX borné mais coûteux, évolution séparée des adaptateurs/export, isolement de charge ; aucune raison d'introduire un writer Carthago. **IAM** justifie un périmètre de credentials et de cycle de sécurité dédié, mais ne doit sortir qu'après contrats et révocation. **Client & CRM** garde un agrégat cohérent et constitue le cœur CRM. **Commercial** a aujourd'hui seulement Opportunity ; son autonomie est une cible explicitement demandée, son gain fonctionnel grandira avec rendez-vous/campagnes/workflows. Ne pas créer un microservice par modèle ou par écran.

Analytics et Audit n'ont pas besoin d'un déploiement supplémentaire aujourd'hui. Analytics reste un module aux APIs filtrées sans formule inventée ; journaux locaux et consolidation Audit restent des modules embarqués avec dépendances explicites. Le Gateway M2 reste une image séparée. Aucun changement du design frontend.

Risques bloquants : (1) révocation/affectation contournée pendant un commit distant ; (2) droits PUBLIC/search_path/role membership ou fonctions donnant accès latéral ; (3) perte d'audit transactionnel ; (4) copie de données et rollback post-commit incomplet ; (5) divergence de contrats React/CSV/Decimal/cookies ; (6) snapshots pris pour des identités source. Mitigations : gates S2, connexions LOGIN séparées/ACL réelles, journal local, backup+deltas et writer unique, manifeste et tests M1/M2, aucun merge source. Docker/TLS/runtime de production et stratégie RPO/RTO/approbation backup restent à valider ; aucune migration de production autorisée ici.

## 8. S1 livré et reproductibilité

`clients/policies.py` possède maintenant `client_queryset`; `identity/policies.py` reste limité aux grants et délégations. Les callers Client sont adaptés ; les mêmes filtres, intersections, verrous et revalidations subsistent. Les tests de contrat refusent une dérive des routes ; un test de dépendance empêche le retour de l'import Client dans IAM policies. Le runtime conserve temporairement les jointures IAM nécessaires ; ce déplacement n'est **pas** une API IAM distante.

`scripts/service_inventory.py` exporte uniquement la structure en transaction READ ONLY. `service_architecture/ownership.py` nomme les propriétaires cibles ; il n'est ni un router Django multi-base ni une ACL SQL de production. `scripts/schema_boundaries.py` refuse une base applicative/non vide/non marquée et n'accepte que le cluster portable local en DEBUG, host 127.0.0.1:55432. Il crée une base temporaire, quatre schémas et douze rôles uniques, teste des données **SYNTHETIC** par connexions authentifiées, puis supprime sa base et ses rôles après vérification des marqueurs. Aucun credential généré n'est écrit dans un rapport ou stdout. Les trois rôles par service n'impliquent pas douze services.

```sh
python scripts/service_inventory.py --output docs/migration/service-inventory.json
python scripts/schema_boundaries.py --confirm-synthetic
python -m unittest discover -s scripts/tests
python scripts/migration_baseline.py --confirm-synthetic --gateway
```

Le rehearsal utilise le propriétaire du cluster portable privé (`.local/postgres/credentials.json`), jamais les credentials runtime en production. Rôles globaux PostgreSQL : noms générés, NOLOGIN owners et cleanup exact par marqueur. Une interruption brutale peut laisser des objets marqués ; les examiner individuellement, ne jamais utiliser de DROP OWNED/CASCADE global ou réexécuter une suppression par préfixe. Un échec de cleanup laisse le gate en échec, même si les probes fonctionnelles passent.

Résultats exécutés le 14 novembre 2026 :

| Vérification | Résultat |
|---|---|
| Schémas/credentials PostgreSQL réels | **20 groupes de contrôles réussis** : quatre migrations propriétaires, quatre CRUD runtime + refus DDL/escalation, douze couples dirigés de refus inter-services ; vérifications supplémentaires des credentials migrateur et fonctions privées. |
| Sécurité du runner | **11 tests unitaires réussis**, dont trois gardes nouvelles refusant base applicative, marqueur absent et base non vide. |
| Backend PostgreSQL | **104/104**, 47,071 s ; contrats, isolation, permissions, révocation concurrente, modèles/imports et quatre nouveaux gates de décomposition. |
| Gateway Nginx réel | **10/10**, 81,928 s ; contrats consommateurs et 38 chemins / 47 méthodes, spoofing, limites, erreurs et rollback direct. |
| Chromium via Gateway | **11/11 DEV**, **6/6 bundle compilé** (43,5 s pour le bundle). |
| Django, migrations, OpenAPI, TypeScript et build Vite | Succès ; aucune migration à créer. |
| M1 backup/restore synthétique | Parité exacte, session restaurée et neuf probes de contraintes réussies ; deux bases scratch supprimées. |
| Base applicative existante | Empreintes avant/après identiques dans le gate complet et dans le rehearsal de schémas. |
| Nettoyage de schémas/rôles | Base temporaire et douze rôles marqués supprimés ; aucun changement d'ACL/ownership applicatif. |

Rapports privés : `.local/service-boundaries/ecebc0aa763346b0a9ee9aab1ee2e549/report.json` et `.local/migration-baseline/09916373931b4f32a81f19e6c9fea9d4/report.json`, tous deux `passed`. Nginx lancé comme processus réel ; Docker et déploiement TLS de production non exécutés sur cette machine. Le protocole advisory/HTTP S2 n'a pas été implémenté ni validé par ces tests.

**Services métier indépendants livrés dans S1 : aucun.** Les frontières de permissions SQL ont été démontrées sur des tables de test synthétiques, pas appliquées aux tables métier courantes. Le premier candidat métier sera Integration en S3 ; aucune bascule avant S2.

## Annexes exhaustives générées

Les annexes suivantes reprennent l'inventaire machine et rendent les propriétaires explicites. Les noms de tables actuels restent dans `public` tant qu'aucune étape de transfert n'a été exécutée.

Fichiers S1 : `backend/clients/policies.py`, callers `clients/{views,services,workspace,prospects}.py`, `identity/policies.py` ; `backend/service_architecture/{ownership,tests}.py` ; `scripts/{service_inventory,schema_boundaries}.py`, `scripts/tests/test_schema_boundaries.py` et ajout de la suite architecture au runner `scripts/migration_baseline.py`. Documentation : ce plan/inventaire, pointeurs de priorité dans les six documents d'audit et le bilan M2, README, architecture et roadmap. Aucun fichier de migration, modèle, URLConf, configuration Nginx/Compose ou source React modifié.

### Tables actuelles et proprietaires cibles

| Table | Proprietaire cible | Schema cible |
|---|---|---|
| `audit_auditevent` | iam | `aiced_iam` |
| `auth_group` | iam | `aiced_iam` |
| `auth_group_permissions` | iam | `aiced_iam` |
| `auth_permission` | iam | `aiced_iam` |
| `clients_crmprofile` | client_crm | `aiced_client_crm` |
| `clients_externalidentity` | client_crm | `aiced_client_crm` |
| `clients_financialaccount` | client_crm | `aiced_client_crm` |
| `clients_interaction` | client_crm | `aiced_client_crm` |
| `clients_legalentity` | client_crm | `aiced_client_crm` |
| `clients_opportunity` | commercial | `aiced_commercial` |
| `clients_party` | client_crm | `aiced_client_crm` |
| `clients_physicalperson` | client_crm | `aiced_client_crm` |
| `clients_prospect` | client_crm | `aiced_client_crm` |
| `django_content_type` | iam | `aiced_iam` |
| `django_migrations` | legacy_registry | `public (historique conserve)` |
| `django_session` | iam | `aiced_iam` |
| `identity_capability` | iam | `aiced_iam` |
| `identity_loginbucket` | iam | `aiced_iam` |
| `identity_membership` | iam | `aiced_iam` |
| `identity_organization` | iam | `aiced_iam` |
| `identity_role` | iam | `aiced_iam` |
| `identity_role_permissions` | iam | `aiced_iam` |
| `identity_roleassignment` | iam | `aiced_iam` |
| `identity_user` | iam | `aiced_iam` |
| `identity_user_groups` | iam | `aiced_iam` |
| `identity_user_user_permissions` | iam | `aiced_iam` |
| `ingestion_importbatch` | integration | `aiced_integration` |
| `ingestion_importpolicy` | integration | `aiced_integration` |
| `ingestion_sourcesnapshot` | integration | `aiced_integration` |
| `ingestion_stagingrow` | integration | `aiced_integration` |

### Routes publiques : methodes, implementation et proprietaire

| Route | Methodes | Proprietaire cible | Vue actuelle |
|---|---|---|---|
| `/api/prospects/` | GET, POST | client_crm | `clients.prospects.ProspectsView` |
| `/api/prospects/context/` | GET | client_crm | `clients.prospects.ProspectContextView` |
| `/api/prospects/<uuid:party_id>/` | GET, PATCH | client_crm | `clients.prospects.ProspectView` |
| `/api/imports/context/` | GET | integration | `ingestion.views.ImportContextView` |
| `/api/imports/<uuid:organization_id>/batches/` | GET | integration | `ingestion.views.BatchListView` |
| `/api/imports/<uuid:organization_id>/upload/` | POST | integration | `ingestion.views.UploadView` |
| `/api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/` | GET | integration | `ingestion.views.BatchView` |
| `/api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/rejections/` | GET | integration | `ingestion.views.RejectionsView` |
| `/api/imports/<uuid:organization_id>/batches/<uuid:batch_id>/publish/` | POST | integration | `ingestion.views.PublishView` |
| `/api/imports/<uuid:organization_id>/policies/` | GET, POST | integration | `ingestion.views.PoliciesView` |
| `/api/imports/<uuid:organization_id>/policies/<uuid:policy_id>/approve/` | POST | integration | `ingestion.views.PolicyApproveView` |
| `/api/imports/<uuid:organization_id>/policies/<uuid:policy_id>/revoke/` | POST | integration | `ingestion.views.PolicyRevokeView` |
| `/api/health/` | GET | platform_contract | `core.views.HealthView` |
| `/api/session/` | GET | iam | `core.views.SessionView` |
| `/api/schema/` | GET | platform_contract | `drf_spectacular.views.SpectacularAPIView` |
| `/api/auth/csrf/` | GET | iam | `identity.views.CsrfView` |
| `/api/auth/login/` | POST | iam | `identity.views.LoginView` |
| `/api/auth/logout/` | POST | iam | `identity.views.LogoutView` |
| `/api/auth/access/` | GET | iam | `identity.views.AccessView` |
| `/api/clients/` | GET | client_crm | `clients.views.ClientListView` |
| `/api/clients/create/` | POST | client_crm | `clients.workspace_views.CreatePartyView` |
| `/api/clients/context/` | GET | client_crm | `clients.workspace_views.ClientContextView` |
| `/api/clients/<uuid:party_id>/workspace/` | GET | client_crm | `clients.workspace_views.WorkspaceView` |
| `/api/clients/<uuid:party_id>/identity/` | PATCH | client_crm | `clients.workspace_views.IdentityEditView` |
| `/api/clients/<uuid:party_id>/profile/` | PATCH | client_crm | `clients.workspace_views.ProfileView` |
| `/api/clients/<uuid:party_id>/interactions/` | GET, POST | client_crm | `clients.workspace_views.ActivityView` |
| `/api/clients/<uuid:party_id>/interactions/<uuid:activity_id>/` | GET, PATCH | client_crm | `clients.workspace_views.InteractionDetailView` |
| `/api/clients/<uuid:party_id>/opportunities/` | GET, POST | commercial | `clients.workspace_views.OpportunitiesView` |
| `/api/clients/<uuid:party_id>/opportunities/<uuid:activity_id>/` | GET, PATCH | commercial | `clients.workspace_views.OpportunityDetailView` |
| `/api/clients/<uuid:party_id>/` | GET | client_crm | `clients.views.ClientDetailView` |
| `/api/clients/<uuid:party_id>/crm/` | PATCH | client_crm | `clients.views.CRMUpdateView` |
| `/api/clients/<uuid:party_id>/accounts/` | GET | client_crm | `clients.views.AccountListView` |
| `/api/organizations/<uuid:organization_id>/users/` | GET, POST | iam | `identity.views.UserListView` |
| `/api/organizations/<uuid:organization_id>/memberships/<uuid:membership_id>/` | PATCH | iam | `identity.views.MembershipStateView` |
| `/api/organizations/<uuid:organization_id>/role-assignments/` | GET, POST | iam | `identity.views.RoleAssignmentView` |
| `/api/organizations/<uuid:organization_id>/role-assignments/<uuid:assignment_id>/` | DELETE | iam | `identity.views.RevokeRoleView` |
| `/api/organizations/<uuid:organization_id>/roles/` | GET | iam | `identity.views.RoleCatalogueView` |
| `/api/audit/` | GET | iam | `audit.views.AuditListView` |

### Relations SQL traversant les nouvelles frontieres

| Table source | Table cible | Contrainte actuelle a remplacer apres API testee |
|---|---|---|
| `clients_crmprofile` | `identity_user` | `FOREIGN KEY (updated_by_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `clients_interaction` | `identity_user` | `FOREIGN KEY (author_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `clients_opportunity` | `identity_user` | `FOREIGN KEY (author_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `clients_opportunity` | `clients_party` | `FOREIGN KEY (party_id) REFERENCES clients_party(id) DEFERRABLE INITIALLY DEFERRED` |
| `clients_party` | `identity_membership` | `FOREIGN KEY (assigned_to_id) REFERENCES identity_membership(id) DEFERRABLE INITIALLY DEFERRED` |
| `clients_party` | `identity_organization` | `FOREIGN KEY (organization_id) REFERENCES identity_organization(id) DEFERRABLE INITIALLY DEFERRED` |
| `clients_party` | `identity_membership` | `FOREIGN KEY (assigned_to_id, organization_id) REFERENCES identity_membership(id, organization_id) DEFERRABLE` |
| `ingestion_importbatch` | `identity_organization` | `FOREIGN KEY (organization_id) REFERENCES identity_organization(id) DEFERRABLE INITIALLY DEFERRED` |
| `ingestion_importbatch` | `identity_user` | `FOREIGN KEY (published_by_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `ingestion_importbatch` | `identity_user` | `FOREIGN KEY (uploaded_by_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `ingestion_importpolicy` | `identity_user` | `FOREIGN KEY (approved_by_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `ingestion_importpolicy` | `identity_user` | `FOREIGN KEY (created_by_id) REFERENCES identity_user(id) DEFERRABLE INITIALLY DEFERRED` |
| `ingestion_importpolicy` | `identity_organization` | `FOREIGN KEY (organization_id) REFERENCES identity_organization(id) DEFERRABLE INITIALLY DEFERRED` |

### References techniques

Les [schemas et privileges PostgreSQL](https://www.postgresql.org/docs/17/ddl-schemas.html) expliquent pourquoi search_path seul ne suffit pas. Les [verrous consultatifs transactionnels](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS) fournissent une primitive a tester pour S2, pas une preuve que le protocole applicatif est deja correct.
