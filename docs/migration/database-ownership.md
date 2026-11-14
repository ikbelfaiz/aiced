# Propriété des données et suppression des couplages SQL

> Nouvelle decision utilisateur apres M2 : cible a quatre services larges sur une instance/base PostgreSQL, schemas et credentials separes. Prospects et interactions appartiennent a Client & CRM. Le [plan de decomposition courant](coarse-services-plan.md) remplace les anciennes recommandations de ce document ; les preuves historiques M1/M2 restent conservees.


**Cible proposée uniquement.** Les tables ci-dessous existent aujourd'hui dans la même base. Noms SQL vérifiés à partir du registre Django, des migrations et des métadonnées locales ; aucune donnée de production consultée ou déplacée. Les migrations historiques restent intactes.

## Propriétaire unique par table

| Tables actuelles | Propriétaire cible | Conservation / transformation planifiée |
|---|---|---|
| `identity_user` | Identity & Access | UUID, hashes de mots de passe, états et dates conservés ; aucun mot de passe réinitialisé. |
| `identity_organization` | Identity & Access | Organisation, parent, code et état actifs autoritaires ; pas d'héritage implicite. |
| `identity_membership`, `identity_roleassignment` | Identity & Access | Références, périmètres, échéances et états exacts. |
| `identity_capability`, `identity_role`, `identity_role_permissions` | Identity & Access | Codes/UUID et associations conservés ; aucun octroi automatique en migrant. |
| `identity_loginbucket`, `django_session` | Identity & Access | Budget HMAC et sessions seulement ici ; préserver validité/expiration et clé requise à la transition. |
| `identity_user_groups`, `identity_user_user_permissions`, `auth_group`, `auth_group_permissions`, `auth_permission` | Identity & Access pour les données d'auth historiques | Conserver, même si ignorées par les autorisations métier. Aucun bypass ajouté. |
| `clients_party`, `clients_physicalperson`, `clients_legalentity` | Client | UUID/identité/sous-types/origine/version conservés. Nouveau discriminateur local prospect et état de préparation avant séparation Commercial. |
| `clients_crmprofile` | Client | Contact/notes/version/date/auteur UUID ; agrégat Client local. |
| `clients_externalidentity` | Client | Liens source/interne existants, unicité conservée ; aucune création automatique par migration. |
| `clients_financialaccount` | Client | Projection locale minimale source read-only, IDs et source_as_of conservés ; pas une position complète. |
| `clients_prospect` | Commercial | Qualification/source/next action/version ; conserver `party_id` comme UUID de référence et PK historique, sans FK distante. |
| `clients_interaction`, `clients_opportunity` | Commercial | IDs, party UUID, auteurs, versions, dates, notes et Decimal exacts. |
| `ingestion_importpolicy`, `ingestion_importbatch` | Data Integration | Acteurs/org UUID, toutes les approbations/dates/statuts/règles/digests et clés d'idempotence conservés. |
| `ingestion_stagingrow`, `ingestion_sourcesnapshot` | Data Integration | Cellules positionnelles/raw, erreurs/warnings/dates normalisées, numéros, clés et provenance conservés ; triggers d'immuabilité locaux. |
| `audit_auditevent` historique | Identity & Access, module audit central | Historique original conservé en append-only avec IDs et corrélations ; ne pas réécrire les acteurs/événements. Nouveaux services possèdent leur propre journal local et outbox, pas un droit d'INSERT dans cette base. |
| `django_migrations`, `django_content_type` et métadonnées techniques futures | Chaque service, localement | Conserver l'historique du backend initial ; chaque nouvelle base possède sa lignée de migrations et content types. Ne pas copier aveuglément tous les content types ou permissions d'apps étrangères. |
| Aucune table actuelle | Reconciliation / Reporting / AI | Chaque futur service crée et migre ses propres tables ; aucune « propriété » fictive sur les tables voisines. |

Les noms des tables cibles peuvent rester identiques à l'intérieur de bases distinctes pour limiter les transformations. Cela ne permet pas de charger les migrations historiques dépendant de User et toutes les autres apps dans chaque service. La stratégie de lignées est décrite plus bas.

## Toutes les FK / relations qui traverseraient ces frontières

| Relation actuelle (colonnes SQL) | Frontière | Remplacement proposé |
|---|---|---|
| `clients_party.organization_id → identity_organization.id` | Client → IAM | UUID immuable ; validation IAM, référence locale minimale d'organisation avec version/état et barrière de désactivation. |
| `clients_party.assigned_to_id → identity_membership.id` | Client → IAM | Membership UUID ; validation propriétaire de l'appartenance à la même org ; référence locale unique `(membership_id, organization_id)` pour FK locale de cohérence. Jamais une nouvelle identité/membership autoritaire. |
| FK SQL supplémentaire `(clients_party.assigned_to_id, organization_id) → identity_membership(id, organization_id)` | Client → IAM | Remplacer par la référence locale même-org seulement après backfill et validation intégrale. Non représentée par une simple FK Django ; migration `clients/0002`. |
| `clients_crmprofile.updated_by_id → identity_user.id` | Client → IAM | Actor UUID validé depuis principal authentifié ; référence conservée après désactivation utilisateur, sans lecture distante de données privées pour afficher l'historique. |
| `clients_prospect.party_id → clients_party.id` (OneToOne/PK) | Commercial → Client | UUID/PK historique + référence Client et opération de préparation/activation ; Client conserve la classification qui protège sa visibilité. |
| `clients_interaction.party_id`, `clients_opportunity.party_id → clients_party.id` | Commercial → Client | Référence Client validée et accès actuel ; versions/état/tombstone. Aucun delete/cascade réseau. |
| `clients_interaction.author_id`, `clients_opportunity.author_id → identity_user.id` | Commercial → IAM | Actor UUID non modifiable par requête ; existence/principal IAM vérifiés lors de la création, attribution historique conservée. |
| `ingestion_importpolicy.organization_id`, `ingestion_importbatch.organization_id → identity_organization.id` | Integration → IAM | Org UUID + référence locale/ligne de garde unique pour quotas et locks ; autorisation IAM live séparée. |
| `ingestion_importpolicy.created_by_id`, `approved_by_id → identity_user.id` | Integration → IAM | Actor UUID ; contraintes locales créateur ≠ approbateur et cohérence approved_by/at maintenues. |
| `ingestion_importbatch.uploaded_by_id`, `published_by_id → identity_user.id` | Integration → IAM | Actor UUID ; déposant ≠ publieur et cohérence de publication toujours contrôlés en SQL local. |
| `audit_auditevent.actor_id`, `organization_id → identity_user/organization.id` | Audit local futur → IAM ; historique reste local à IAM | Historique gardé chez IAM avec ses FK. Journaux des autres services : UUID, pas de FK distante ; événement créé dans la transaction du producteur, copié idempotemment vers le central. |
| `audit_auditevent.target_id` | Référence logique existante vers plusieurs domaines | Déjà UUID sans FK ; conserver et ajouter au protocole futur le producteur/type d'objet sans réécrire les anciennes lignes. |

Relations **intra-propriétaire à garder** : IAM Organization.parent, Membership→User/Organization, RoleAssignment→Membership/Role et M2M rôles/capacités ; Client sous-types/CRM/ExternalIdentity/FinancialAccount→Party ; Integration Batch→Policy, Row→Batch, Snapshot→Row. Les tables d'auth Django restent IAM. Il n'existe aucune FK Integration→Client, ni table de rapprochement à transférer.

Après extraction, les références locales n'accordent jamais des droits. Les organisations/memberships désactivés restent identifiables mais inaccessibles. Les références d'organisation/membership ne sont pas réaffectables à une autre organisation ; s'il faut changer d'organisation, créer une nouvelle référence autorisée. Pas de suppression physique des sujets portant un historique protégé sans politique approuvée.

## Jointures Python / SQL qui ne sont pas des FK explicites

| Couplage actuel | Remplacement |
|---|---|
| `identity.policies.client_queryset` : User/Role/Membership → Party → Prospect | IAM expose grants ; Client applique scopes/affectation et classification prospect locale. Les autres services appellent le contrat d'accès Client, pas son ORM. |
| Répertoire `prospect__isnull=True`, Workspace `hasattr(party,'prospect')` | Backfill Client classification depuis les PK Prospect existantes avant séparation ; clients AICED ordinaires inchangés, aucune conversion en identité source. |
| ProspectOutput : nom/type/created_at/assigned_to.user.username | Résumé Client autorisé et référence de manager IAM minimale ; respecter nullable. Pas d'accès direct aux Users pour une simple liste. |
| `prospect_queryset` sous-requête Interaction + droits | Qualification et interactions restent Commercial ; périmètre Client obtenu avant recherche/count/pagination ; date masquée sans interactions.view. |
| Workspace dernière date account + CRM/sous-type | Reste local Client ; ne pas exposer source_as_of au demandeur sans finance sur cet objet. |
| `ingestion.views.BatchView` lit AuditEvent | Historique local Integration avec reprise des événements historiques concernés ou API centrale autorisée pendant transition ; UUID/corrélations conservés, pas de double événement logique. |
| `core.errors` et toutes mutations importent `audit.services.record` | Façade de journal local, même transaction/connexion que le domaine ; livraison outbox vers le central. |
| Seeds/tests instancient des modèles de plusieurs apps | Jeux synthétiques par service et fixtures de contrats ; tests inter-services séparés. Ne pas en faire un mode de bootstrap multi-base de production. |

## Transactions et verrous traversant les futures frontières

| Transaction actuelle | Garantie à conserver / stratégie |
|---|---|
| IAM assign/revoke/create_user/set_membership_state + Organization lock + AuditEvent | IAM garde ses écritures et son journal dans sa transaction ; coordonne révocation/admission distante selon [la cible](target-architecture.md). |
| login_session : session + audit ; logout_session : logout + audit | Garder sessions/audit local IAM et gestion d'erreur ; ne pas déplacer les sessions au Gateway ou partager la SECRET_KEY entre tous les services. |
| create_party : Organization lock + Party + sous-type + CRM + audit | Agrégat Client local ; références IAM prévalidées et droits courants coordonnés ; triggers de sous-type toujours différés dans la transaction locale. |
| update_crm/edit_profile/edit_identity : Organization lock + Party/profil + audit | Version/verrous locaux Client et journal ; revalidation de droits après attente, avec protocole de révocation, pas une copie de grants périmée. |
| create_prospect : Organization + create_party imbriqué + Prospect + deux audits | N'est plus atomique en SQL. Orchestration durable/idempotente Commercial + préparation/activation Client ; détails ci-dessous. |
| edit_prospect/save_activity : Organization + Party lock + Prospect/Interaction/Opportunity + audit | Opération locale Commercial avec validations Client/IAM et admission suivie jusqu'au commit/rollback. Maintenir contrôle UUID activité ET party, pas seulement UUID activité. |
| stage : parse hors transaction puis Organization + Batch/Rows + audit | Parse conservé ; garde locale org pour idempotence/quota + autorisation distante cohérente. Aucun lock distribué autour du traitement ZIP complet. |
| create/approve/revoke_policy/publish : Organization + Policy/Batch/Rows/Snapshots + audit | Toutes données de publication restent Integration : transaction locale, garde org, règles double acteur, replay et triggers. Seule l'autorisation est distante. |

Une nouvelle connexion PostgreSQL ou un `transaction.atomic()` imbriqué dans un autre service ne participe pas à la transaction initiale. Aucun two-phase commit requis ; ne pas simuler cette atomicité par deux HTTP et un rollback supposé.

## Création de prospect sans identité orpheline visible

1. Commercial valide le corps et les droits équivalents, crée une opération durable à clé idempotente. Les retries internes portent la même clé et le même digest de commande ; conflit si même clé/corps différent.
2. Client prépare un contact **pending/prospect**, avec Party/sous-type/CRM/audit dans sa transaction locale. Ce contact n'est visible dans aucun répertoire, workspace, recherche ou rapport ordinaire. Il n'est jamais classé client par défaut.
3. Commercial crée la qualification et son audit local, liés à l'opération/UUID. Ses lectures filtrent aussi sur l'activation Client ; elles ne publient pas une qualification d'un sujet pending.
4. Client active atomiquement le contact seulement après receipt durable de qualification Commercial. Comme Client contrôle la visibilité et Commercial possède déjà la qualification, l'activation devient le point de publication logique. Acquitter 201 seulement après activation confirmée ; retries récupèrent le même résultat.
5. En panne, rejouer/reprendre l'opération et garder le contact caché. Annuler/archiver une préparation avec historique, **pas supprimer silencieusement une identité ou un audit**. Après activation, aucune compensation destructive ; résolution/replay explicites. Tester les pannes à chaque transition et l'absence de contact actif sans qualification.

Ces états et tables d'opération sont à construire ; ils n'existent pas aujourd'hui. Le corps JSON existant reste compatible. Une clé d'idempotence optionnelle côté client HTTP peut améliorer la reprise d'un timeout utilisateur sans redesign ; l'opération interne reste obligatoirement idempotente. Aucune déduplication d'identité par nom ou égalité approximative de corps.

## Migrations, copie et preuves d'intégrité

- Conserver **tous** les fichiers actuels et l'historique `django_migrations` du backend initial. Aucune édition des anciennes migrations, aucun reset/squash/`--fake` de convenance. Les dépendances actuelles vers AUTH_USER_MODEL et identity/0002 empêchent de copier simplement le dossier ingestion dans un projet vide.
- Créer ultérieurement une lignée de migration initiale propre à chaque nouveau déploiement, avec modèles adaptés aux UUID distants et seulement ses tables. Les noms db_table historiques peuvent être conservés. Pour le résidu Client, migrations additives/state-only (`SeparateDatabaseAndState` si justifié et testé) et suppression ultérieure des FK distantes ; ne pas appliquer un DeleteModel qui détruirait les données extraites.
- Copy-order Integration : Policy → Batch → Rows → Snapshots ; Client : références locales → Party → sous-types/CRM/comptes/liens ; Commercial : références → qualifications/activités ; IAM : User/Org/Capabilities/Roles → Memberships/Assignments/M2M puis sessions/budgets/audit. Préserver UUID, dates auto_now/auto_now_add, NULL, versions, textes, Decimal, JSON/raw et contraintes. COPY/outil dédié doit préserver les timestamps au lieu d'utiliser des saves ORM qui les remplacent.
- Une sauvegarde chiffrée approuvée et une restauration isolée vérifiée précèdent toute copie de production. N'extraire que les tables du propriétaire, pas cloner tout le CRM dans chaque service. Préserver fonctions/triggers/index/contraintes, séquences éventuelles et permissions d'exécution ; pas de désactivation globale des protections pour faciliter la copie.
- Contrôler comptes par table/org, ensembles de PK, nullabilité, FK locales, mêmes IDs d'acteurs et cibles, relations same-org, sous-types, digests de lots et cellules, versions/statuts, comptes/décimaux et audit. Calculer les empreintes dans un périmètre privé approuvé ; ne pas publier de hashes de données personnelles dans le dépôt.
- Un seul writer par domaine à chaque instant. Première bascule avec fenêtre d'écriture suspendue sur le domaine, pas de double écriture applicative. La procédure de rollback après nouveaux commits est différente d'un simple retour de route : voir [le plan](migration-plan.md).
