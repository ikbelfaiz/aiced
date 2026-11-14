# Frontières des services et contrats

> Nouvelle decision utilisateur apres M2 : cible a quatre services larges sur une instance/base PostgreSQL, schemas et credentials separes. Prospects et interactions appartiennent a Client & CRM. Le [plan de decomposition courant](coarse-services-plan.md) remplace les anciennes recommandations de ce document ; les preuves historiques M1/M2 restent conservees.


Proposition d'extraction, aucune séparation effectuée. Les noms de contrats internes/futurs ci-dessous sont des **besoins de conception**, pas des endpoints déjà disponibles ni des API Carthago supposées. [Routes actuelles](current-architecture.md#inventaire-des-routes-publiques-actuelles), [tables et FK](database-ownership.md).

## 1. Identity & Access Service

| Aspect | Décision proposée |
|---|---|
| Code existant | `identity/models.py`, `authentication.py`, `services.py`, `views.py`, `serializers.py` ; endpoints session de `core/views.py` ; audit central historique et sa lecture. |
| Données propres | User, Organization, Membership, Capability, Role, RoleAssignment, LoginBucket, associations de rôles et tables Django d'auth/session. Journaux IAM et projection d'audit central. |
| API publique conservée | `/api/session/`, `/api/auth/{csrf,login,logout,access}/`, routes `/api/organizations/{org}/…`, `/api/audit/`. |
| Contrats internes requis | Introspection/authentification du principal, grants effectifs versionnés par organisation, validation d'une référence user/membership/org, admission/révocation cohérente ; ingestion idempotente des événements d'audit minimaux. Aucun endpoint de copie universelle des grants de tous les employés. |
| Dépendances sortantes | Aucune base Client. Sortir `client_queryset()` de ce domaine : IAM décide les grants, Client décide leur application aux objets. Audit consolidé reçoit des journaux, sans lire leurs bases. |
| Frontend | AuthProvider, LoginPage, session/grants, permissions d'affichage, CSRF de chaque mutation. Aucun changement de routes/design ni de stockage des credentials. |
| Sécurité | Conserver refus par défaut, scopes sans héritage, interdiction d'auto-délégation/élévation et limites de durée, rotation/login/logout, budgets PostgreSQL atomiques. Pas de bypass Django staff/superuser. |
| Risques / moment | Très couplé aux FK User/Organization et au verrou de révocation. Préparer l'API de sécurité avant toute extraction ; extraire le stockage IAM après la première extraction Integration validée. Préserver les sessions existantes et leurs secrets uniquement chez IAM après bascule. |

## 2. Client Service

| Aspect | Décision proposée |
|---|---|
| Code existant | `clients/models.py` pour Party, sous-types, CRMProfile, ExternalIdentity, FinancialAccount ; `views.py`, `serializers.py`, `services.update_crm`, parties identité/profil/workspace de `workspace.py` et `workspace_views.py`. Application des scopes aujourd'hui dans `identity/policies.py`. |
| Données propres | Registre Party et classification client/prospect/pending, sous-types, profil CRM, affectation par membership UUID, liens externes et projections minimales de comptes locaux. Source autoritaire Carthago toujours extérieure/read-only. |
| API publique conservée | `/api/clients/`, `/create/`, `/context/`, `/{id}/`, `/{id}/{workspace,identity,profile,crm,accounts}/`. Les sous-routes activités vont à Commercial. |
| Contrats internes requis | Résumé autorisé de contact et organisation/affectation/classification/version ; validation d'objet et d'accès, requête de périmètre pour listes Commercial ; préparation/activation idempotente d'un nouveau contact prospect par opération. Aucun accès générique non filtré à tous les clients. |
| Dépendances | IAM courant pour grants et références ; événements minimaux de classification/affectation à Commercial. Le discriminator prospect doit être local au registre Client : ne pas faire une requête Commercial non fiable pour décider si une identité est visible. |
| Frontend | ClientsPage, CreateClient, ClientWorkspace, compteur Dashboard. JSON Workspace identique, dont is_prospect, ownership, permissions et provenance ; listes d'activités déjà séparées. |
| Sécurité | clients.view intersecté avec l'action, finance et prospects.view sur le même objet. Édition d'identité uniquement AICED sans lien externe ; comptes API GET-only. Aucun changement de mapping/propriété source. |
| Risques / moment | Sous-types et CRM restent un agrégat transactionnel local. Défaire les liens IAM sans perdre same-org ; sortir la qualification Commercial sans exposer les prospects par la route clients. Le résidu historique devient Client Service après extraction IAM/Commercial ; pas de copie réécrite du module complet. |

## 3. Commercial Service

| Aspect | Décision proposée |
|---|---|
| Code existant | Prospect, Interaction, Opportunity dans `clients/models.py` ; `clients/prospects.py`, `workspace.save_activity`, inputs/outputs/vues d'activités dans `workspace.py` et `workspace_views.py`. |
| Données propres | Qualification Prospect (PK historique = UUID Party conservé), interactions, opportunités, auteurs UUID, versions ; plus tard appointments/reminders/campaigns. Références Client minimales et opérations de création en cours, pas une deuxième identité modifiable. |
| API publique conservée | `/api/prospects/`, `/context/`, `/{party}/` ; `/api/clients/{party}/interactions[/id]/` et `/opportunities[/id]/`. Ne pas renommer ces chemins en `/commercial/` dans React. |
| Contrats internes requis | Client fournit contact autorisé, périmètre et version de classification/affectation ; orchestration idempotente de création d'un prospect. Commercial ne crée pas Party par SQL ni par import Python. |
| Dépendances | IAM (principal/grants actuels), Client (existence, scope, identité, affectation, exclusion des contacts pending). Le calcul last_interaction reste Commercial, conditionné par interactions.view. |
| Frontend | ProspectsPage et onglets d'activité ClientWorkspace. Le format date/notes/montant Decimal et les versions ouvertes dans les éditeurs restent identiques. |
| Sécurité | Lecture clients.view + prospects.view si contact prospect ; interactions/opportunities.view et manage sur le même objet. Auteur/org/provenance non injectables ; aucune finance héritée du rôle commercial. |
| Risques / moment | Création de prospect actuellement atomique avec Party/sous-type/CRM/audits ; joints pour nom, manager et pagination. Extraire après référentiel Client/classification et IAM prêts ; conserver corps/réponses API avec un orchestrateur interne, pas une saga pilotée par le navigateur. |

## 4. Data Integration Service

| Aspect | Décision proposée |
|---|---|
| Code existant | `ingestion/models.py`, `parser.py`, `templates.py`, `services.py`, `views.py`, `sources.py`, migrations et tests d'import. Réutilisables avec adaptation des dépendances IAM/audit. |
| Données propres | ImportPolicy, ImportBatch, StagingRow, SourceSnapshot ; templates versionnés actuellement en code ; journal local/historique et outbox. Futurs checkpoints/runs de synchronisation read-only. |
| API publique conservée | Toutes les routes `/api/imports/…`, upload brut, preview JSON, historique et CSV de rejets inclus. |
| Contrats internes requis | IAM pour principal, droits/full scope et noms des organisations autorisées. Snapshot publié consultable par consommateur explicitement autorisé, avec org, version/provenance et pagination ; pas de dump public inter-organisations. |
| Dépendances | IAM ; journal local et consolidation audit. **Pas de dépendance Client requise** pour publier les snapshots : clients.view_financial est un code de capacité IAM, pas un besoin de lire FinancialAccount. |
| Frontend | DataManagement, importApi de workspace-api.ts, lien de téléchargement CSV natif ; préserver modes et filtres de rejets. |
| Sécurité | imports.view ET clients.view_financial full-organization dans la même org, plus capacité d'action. Règle approuvée par un autre créateur, publication par un autre déposant ; aucun droit IT implicite. Snapshot immutable-only. |
| Risques / moment | FK IAM, audit central/historique, verrou Organization utilisé pour quotas/idempotence/révocation. Remplacer le verrou de sérialisation locale par une ligne locale de garde d'organisation ; ce verrou ne remplace pas la barrière de révocation distante. **Premier domaine à extraire après les prérequis sécurité/audit**, d'abord shadow synthétique. |

L'import automatique futur est une seconde voie d'acquisition dans ce même service, pas un service Carthago d'écriture. Réutiliser validation/staging/revue/publication ; les modalités réelles d'accès et le mapping restent à approuver. Le stub ManualExcelSource ne doit pas masquer ou remplacer le parser HTTP opérationnel lors de l'extraction.

## 5. Reconciliation Service

| Aspect | Décision proposée |
|---|---|
| Code existant | Aucun app/table/endpoint. Les descriptions dans `docs/data-integration.md` sont une intention, pas du code à déplacer. |
| Données propres futures | Cas, propositions, décisions append-only, politiques de mapping/propriété approuvées, références de snapshot/Party et receipts d'application idempotents. Aucun duplicata autoritaire des identités/comptes. |
| API | Aucune publique actuelle à préserver. Futures API revue/décision et commandes internes à spécifier ; exposition Gateway seulement après tests et règles approuvées. |
| Dépendances | Snapshots autorisés d'Integration, candidats autorisés de Client, IAM. Commander au propriétaire une modification locale explicitement approuvée ; ne jamais modifier ses tables. |
| Frontend | Aucune page de rapprochement implémentée. DataManagement ne devient pas une page de rapprochement par changement de label. |
| Sécurité | Périmètre de toutes les sources/candidats, justification et séparation des tâches à définir ; pas d'activation des capabilities proposées dans la documentation sans workflow testé. |
| Risques / moment | Fusion incertaine, fausse correspondance de clés Excel et écrasement de source. **Plus tard**, nouveau service, après approbation des règles ; son absence ne bloque pas le CRM ni les snapshots. |

## 6. Reporting Service

| Aspect | Décision proposée |
|---|---|
| Code existant | Aucun modèle/API dédié. Dashboard React ne constitue pas ce backend ; son compteur Client peut rester inchangé. |
| Données propres futures | Projections/agrégats minimaux, définitions KPI versionnées approuvées, dates de fraîcheur, jobs/exports autorisés. Pas de copie financière totale par défaut. |
| API | Futures requêtes/rapports Gateway à définir avec les KPI ; aucune ancienne route à casser. |
| Dépendances / frontend | APIs/événements autorisés Client et Commercial, données source uniquement si approuvées, IAM ; futur Pilotage Managérial, Dashboard conservé jusqu'au remplacement testé des indicateurs. |
| Sécurité | Filtrage avant agrégation, comptage et export ; révocation immédiate et absence de fuite dans cache/agrégats multi-org. Aucun accès financier dérivé automatiquement d'un rôle IT/reporting. |
| Risques / moment | Définition des KPI absente, chiffres fictifs pris pour des faits, projections trop larges. **Plus tard**, quand les formules et utilisateurs autorisés sont validés. |

## 7. AI Service

| Aspect | Décision proposée |
|---|---|
| Code existant | Aucun backend IA, index ou fournisseur configuré ; composants UI indisponibles/illustratifs seulement. |
| Données propres futures | Index/document metadata minimisés, références/provenance, exécutions et politiques de rétention approuvées ; pas de copie universelle du CRM. |
| API | Futures interfaces Gateway à définir. Aucun endpoint existant à extraire. |
| Dépendances / frontend | APIs autorisées de leurs propriétaires, IAM, fournisseur/rétention à approuver ; futurs écrans IA, aucun redesign des pages actuelles. |
| Sécurité | Autorisation à l'indexation ET à chaque retrieval/réponse/citation, revalidation des accès révoqués, prévention des fuites inter-organisations et de l'exfiltration par document. |
| Risques / moment | Données sensibles, injection documentaire, rétention fournisseur non définie, scores inventés. **Futur**, hors première migration. |

## Contrats transversaux à figer

- Bibliothèque technique limitée aux envelopes/validation d'identité et contrats versionnés ; pas d'ORM partagé ni de service « utils » détenteur de toutes les données.
- IDs, états, chaînes Decimal, précision des dates, corps/erreurs et pagination actuels restent publics. L'authentification interne, les références et les états de préparation sont privés.
- Versions des enregistrements et des autorisations sont distinctes : une version CRM valide n'autorise pas une écriture après révocation.
- Pagination Commercial : autoriser le périmètre Client avant comptage et recherche. Une liste de 50 candidats filtrée après pagination n'est pas équivalente. Prévoir une requête de périmètre bornée/versionnée ou une projection de références contrôlée par sa fraîcheur ; fail closed si la révision Client ne peut être confirmée. Aucun index de noms/affectations n'est une autorité de permissions.
- L'audit local fait partie de chaque transaction. Le contrat de consolidation est idempotent par producteur/event_id, transporte la provenance et respecte les restrictions de consultation historiques.
