# Plan de migration réversible par étapes

> Nouvelle decision utilisateur apres M2 : cible a quatre services larges sur une instance/base PostgreSQL, schemas et credentials separes. Prospects et interactions appartiennent a Client & CRM. Le [plan de decomposition courant](coarse-services-plan.md) remplace les anciennes recommandations de ce document ; les preuves historiques M1/M2 restent conservees.


Suivi d'exécution : **M1 implémenté et vérifié sur une répétition synthétique isolée**, voir [le bilan](m1-baseline-status.md). M2 et les extractions restent à réaliser. Le texte de cadrage ci-dessous provient de l'audit initial ; il ne décrit pas les résultats d'exécution ultérieurs. Aucune autorisation de copie de production n'est déduite du gate de développement.

**Analyse et proposition seulement — aucune étape technique exécutée dans cette intervention.** M0 correspond aux documents de l'audit. Les étapes suivantes sont des futurs lots séparés et révisables. La demande utilisateur prévaut sur l'ancienne décision monolithe ; les fonctionnalités et migrations existantes sont le point de départ, pas du code à remplacer.

## Ordre et résultat visé

M0 audit → M1 référence/contrats → M2 Gateway transparent → M3 journal/outbox local → M4 frontière IAM et concurrence → M5 Integration shadow → M6 Integration actif → M7 IAM indépendant → M8 Commercial indépendant → M9 Client résiduel indépendant. **M9 atteint le minimum viable : Gateway + IAM + Client + Commercial + Integration, quatre bases propriétaires.** Reconciliation, Reporting et AI suivent avec leur métier ; pas de conteneurs vides pour prétendre les avoir livrés.

L'extraction de Data Integration est la première extraction de domaine parce que ses snapshots n'ont aucun lien Client/compte. IAM est préparé en premier comme contrat de sécurité mais son déplacement physique attend les garanties de révocation et les adaptations des références. Extraire seulement le parser dans un processus ne vaut pas extraction du service de données.

## Règles communes de passage et retour

- Chaque étape a son PR/lot, contrat versionné, tests et revue. Ne pas combiner refonte de framework, nouveaux KPI, intégration Carthago et extraction dans la même étape.
- Avant écriture/copie **de production** : accord sur propriétaire de sauvegarde, fenêtre de gel, RPO/RTO, chiffrement/accès/rétention, sauvegarde approuvée et restauration vérifiée isolément. Les valeurs de RPO/RTO et l'approbation ne sont pas connues ; aucune opération de production autorisée par ce plan.
- Un seul writer par domaine. Basculer de manière explicite et atomique les routes **et** les jobs/credentials ; les instances anciennes doivent être clôturées ou privées d'écriture. Ne pas compter sur la seule configuration du Gateway si un chemin interne reste actif.
- Tout écart de périmètre, de révocation, de données, de source-owned ou d'audit bloque la bascule, même si les pages s'affichent. La disponibilité ne justifie pas une autorisation périmée.
- Deux rollbacks différents : **avant premier commit nouveau**, arrêter le candidat et restaurer les routes vers l'ancien writer inchangé ; **après nouveaux commits**, geler, conserver journaux/outbox/receipts, transférer ou rejouer les deltas validés vers le writer de repli, réconcilier et tester, puis seulement rerouter. Restaurer aveuglément une ancienne sauvegarde ou simplement rerouter ferait perdre des données.
- Si le transfert inverse n'a pas été éprouvé ou n'est pas sans perte, maintenir le gel et corriger en avant ; ne pas annoncer un rollback sûr. Les anciennes tables restent en rétention protégée pendant la fenêtre approuvée, pas un writer secondaire.

## M0 — Audit documentaire (cette intervention)

**Livrables :** les six documents de migration, correction du statut de `docs/architecture.md`, roadmap actualisée. Inventaire réel des routes/tables/FK, contraintes, transactions et tests.

**Acceptation :** références du code et métadonnées cohérentes ; distinguer code existant, cible et inconnues ; aucun changement runtime/migration/données. Contrôles de cohérence Django/OpenAPI en lecture seule documentés dans [l'état actuel](current-architecture.md).

**Retour :** retirer ou corriger uniquement ces documents. Aucun rollback de base nécessaire. L'audit n'autorise pas la bascule suivante.

## M1 — Figer la référence et prouver la restauration

**Travail futur :** constituer un manifeste des routes réelles (méthodes, statuts, erreurs, schémas et champs non décrits par OpenAPI), des migrations/contraintes/triggers, des IDs/versions et jeux synthétiques. Extraire les fixtures partagées de tests sans modifier les règles. Faire approuver puis répéter backup/restore sur l'environnement autorisé. Documenter l'empreinte de code et la version de la sauvegarde dans un espace privé.

**Acceptation :** suite PostgreSQL actuelle et E2E synthétiques à nouveau exécutées, pas seulement les anciens rapports ; parité de la restauration (IDs, FK, triggers, audit, digests, versions, snapshots, sessions) et récupération des secrets selon procédure sécurisée. Contrats Consumer tests de toutes les fonctions `api`, `workspaceApi`, `importApi` et appels directs Prospects ; rejets 403/404/cross-org/finance/prospect obligatoires.

**Retour :** supprimer uniquement l'environnement de répétition explicitement identifié, sans toucher la source ; archiver les preuves privées. Si restauration non démontrée, arrêter la migration et conserver le runtime courant.

## M2 — Introduire le Gateway sans répartir les données

**Travail futur :** proxy même origine, toutes les routes vers le backend courant. Pas de changement des pages ou URL. Ajouter limites/délais spécifiques JSON/XLSX, no-store, erreurs d'amont compatibles ; traiter de manière contrôlée TLS/Origin/Host/IP et headers de confiance. Désactiver les retries automatiques des mutations.

**Acceptation :** tests de contrat direct/proxy équivalents ; login, rotation CSRF, logout, expiration, rate limits réels (pas les seuils relevés du runner UI), headers forgés, upload 10 Mio/rejet supérieur, CSV et replays. Routes protégées non accessibles par contournement réseau ; contraintes de proxy testées avant de publier les ports. Aucun changement de données ni d'images/rôles métier.

**Retour :** retirer le proxy de la chaîne/rétablir l'origine précédente, en conservant cookies/session/path compatibles ; aucune base n'a changé. Ne pas basculer login si le contrat de client IP ou TLS n'est pas validé.

## M3 — Préparer journal local, consolidation et outbox

**Travail futur :** introduire une interface technique d'audit qui continue d'écrire dans la transaction courante. Préparer journaux locaux append-only, outbox à état de livraison séparé et inbox/déduplication par producteur/event_id. Un worker HTTP simple suffit ; aucun Kafka requis. Adapter l'historique des imports pour qu'il puisse provenir du journal local. Le journal historique n'est pas réécrit.

**Acceptation :** panne d'audit local annule la mutation ; panne de consolidation ne perd aucun événement local ; replay après crash ne duplique pas ; payload différent sous le même event_id rejeté/quarantiné. Conserver actor/org/target/request IDs et refus anonymes, éviter notes/cellules/secrets. Consultation scoped et historique immédiat du lot testés. Faire valider le retard éventuel de `/api/audit/`, ou prévoir lecture autorisée fédérée avant bascule.

**Retour :** tant qu'aucun domaine n'est extrait, garder `audit.services.record` historique comme writer. Stopper le worker, drainer/réconcilier les événements déjà émis sans les supprimer. Les migrations nouvelles sont additives et compatibles avec l'ancien code ; pas d'unapply supprimant l'historique.

## M4 — Construire et tester le contrat IAM avant déplacement

**Travail futur :** une façade interne IAM dans le backend existant, principal délégué vérifiable, validation CSRF/session, grants versionnés, références d'organisation/membership et révocation/admission cohérente. Séparer la décision de grants de la construction des querysets Client. Préparer les modèles de références locales et le discriminateur prospect Client, sans suppression des anciennes FK.

**Acceptation :** fausse identité/service/audience/replay refusés ; mêmes intersections assigned/organization/finance/prospect ; pas d'élévation via delegation. Rejouer le scénario `RevocationRaceTests` sur deux services/bases : un write en attente ne survit pas à la révocation validée. Crash entre décision/commit, partition réseau, session/logout, org/membership désactivé, rôle expiré et permis non résolu testés. Timeout ferme l'accès et ne donne pas un succès de révocation mensonger. Contrat de fraîcheur avant count/pagination pour Commercial spécifié. Aucun token de longue durée pris comme autorité complète.

**Retour :** désactiver l'adaptateur distant et reprendre les contrôles ORM/verrous actuels pour les chemins encore monolithiques ; aucun writer extrait actif à ce stade. Conserver les colonnes additives. Si l'équivalence sécurité n'est pas démontrée, rester ici pour les écritures plutôt que contourner le gate.

## M5 — Extraire Data Integration en candidat isolé

**Travail futur :** image/settings/URLConf/DB/role/migrations/tests propres. Réutiliser parser, templates, validation et publication ; remplacer FK IAM par UUID/références locales, Organization lock de quota/idempotence par garde locale, AuditEvent par journal local. API IAM servie par le backend historique pendant cette transition. Publication reste snapshot-only.

**Acceptation :** démarrage/migrations depuis base vide contenant seulement tables propriétaires/techniques ; le service ne peut pas ouvrir ni modifier la base historique. Suite isolée sans imports de `identity.tests` ou modèles Client ; tests de contrats IAM et tests d'intégration réels séparés. Fichiers malformés/ZIP/XML/formules, dates/doublons/rejets, quota, double acteur, concurrence/replay/rollback et triggers vérifiés. Contrats React byte/schema et CSV comparés sur données synthétiques. Stopper/redéployer Integration sans reconstruire le backend Client/IAM.

**Retour :** arrêter le candidat, garder tout trafic réel historique. Les données du candidat sont synthétiques et isolées ; aucune copie de production pendant ce shadow sans la procédure M1 approuvée.

## M6 — Basculer le domaine Integration, un writer

**Travail futur :** après sauvegarde/restauration approuvées, geler uploads/règles/publications/jours d'import et futurs jobs. Copier uniquement les tables Integration et les métadonnées d'audit nécessaires ; préserver IDs, raw, dates, version du template, clé d'idempotence complète, policy/status et triggers. Valider, router toutes les routes `/api/imports/` vers le nouveau service puis ouvrir son writer. Backend historique ne détient plus le droit d'écriture Integration. IAM reste temporairement dans le résidu, accessible par API.

**Acceptation :** égalité des ensembles de PK et invariants par organisation, import historique consultable, upload du même fichier retourne le même lot, publication/rejeu pas de nouveau snapshot, règles/exclusions identiques, comptes/identités strictement inchangés. Refaire le parcours E2E opérateur/reviewer via Gateway, erreurs réseau et révocation. Audit durable complet et consolidation contrôlée. Les credentials Integration ne donnent accès qu'à sa base.

**Retour :** avant réouverture, reprendre l'ancien writer. Après nouveaux commits, geler et appliquer le rollback post-commit commun avec outil inverse testé : nouvelles lignes/snapshots/audits insérés avec leurs IDs ; lignes immuables déjà présentes comparées, jamais UPDATE/DELETE pour faciliter le replay ; états modifiables policy/batch transférés transactionnellement dans l'ordre validé. Sans preuve d'intégrité, garder le gel/corriger en avant. Ancienne sauvegarde seule insuffisante.

## M7 — Déployer Identity & Access indépendamment

**Travail futur :** adapter les références IAM du résidu Client/Commercial avec migrations additives et contrôles complets ; remplacer toutes les jointures de grants et locks IAM par les contrats M4 testés. Copier IAM/session/budgets/audit historique dans sa base propriétaire, en préservant UUID, password hashes, expiration et clés nécessaires à la validation des sessions actuelles. Secret d'auth uniquement chez IAM après transition ; ne pas le partager comme méthode d'auth inter-services.

**Acceptation :** connexion existante continue tant qu'elle est valide ; login/logout/rotation, throttle et non-élévation identiques ; révocation cohérente dans Integration et résidu. Chaque service utilise seulement son credential, aucun ORM User/RoleAssignment distant. Références same-org et audit immuable testés ; organisation désactivée immédiatement inaccessible. APIs publiques IAM et `/api/audit/` compatibles. Déployer IAM seul sans migration/reconstruction obligatoire des autres services.

**Retour :** geler création utilisateur, grants/memberships et changements de session concernés ; conserver les décisions de sécurité les plus récentes. Avant commits : routes/secrets précédents restaurables. Après commits : replay validé de sessions, grants, révocations, budgets et audit vers l'ancien propriétaire, ou correction en avant. Ne jamais réactiver un accès révoqué en restaurant une ancienne copie IAM. Ne pas invalider silencieusement toutes les sessions pour simplifier la migration.

## M8 — Déployer Commercial indépendamment

**Travail futur :** Client conserve identité/classification/affectation ; Commercial reçoit Prospect/Interaction/Opportunity, auteurs et UUID Client, versions et Decimal exacts. Introduire l'opération de préparation/activation du prospect décrite dans [database-ownership](database-ownership.md#création-de-prospect-sans-identité-orpheline-visible). Garder les routes publiques imbriquées sous clients au Gateway. Composition des résumés/périmètres via API Client, jamais SQL.

**Acceptation :** suite isolée Commercial et contrats Client/IAM ; Client inaccessible/affectation ou permission modifiée → aucun accès indu. Recherches et compteurs filtrés avant pagination, dernière interaction masquée sans sa permission. Tests de panne à chaque transition de création et replay, zéro prospect actif orphelin ou apparaissant comme client ordinaire. Scénarios édition/version et montants TND, activités dont UUID appartient à un autre party, données historiques et E2E prospect → interaction → opportunité identiques. Arrêter Commercial ne bloque pas login/import/CRUD Client non dépendants ; les actions Commercial échouent proprement, pas un faux succès.

**Retour :** geler créations/qualifications/activités et opérations en cours ; résolution ou maintien caché des préparations. Copier les nouveaux commits/versions/audits avec correspondance éprouvée, ne pas supprimer Party pour compenser. Reprendre l'ancien writer uniquement après réconciliation, protections prospect maintenues dans Client. Si une opération ne peut être représentée dans l'ancien schéma, correction en avant.

## M9 — Finaliser le Client Service et valider le checkpoint MVP

**Travail futur :** le résidu historique devient Client ; retirer les apps/runtime/credentials des domaines déjà extraits sans supprimer leurs anciennes migrations ni leurs archives. Base Client ne conserve que ses tables autoritaires, références minimales et journal/outbox. Les tables historiques déplacées ne sont purgées qu'après rétention/rollback approuvés, dans une opération distincte. Durcir images/health/readiness/serveur applicatif et proxy pour le déploiement prévu ; Compose suffit.

**Acceptation :** quatre services démarrent chacun avec leur seule base et tests propres ; déploiements/migrations indépendants et compatibilité N/N-1 des contrats. Frontend inchangé visuellement, toutes ses routes et APIs historiques passent via Gateway. Tests directs/proxy, isolation, révocation, rollback, audit et source-read-only passent. Échec d'un service ne produit ni droits élargis ni valeurs fictives. Sauvegarde/restauration par propriétaire, journaux et alertes/outbox éprouvés ; les anciennes suites monolithiques restent conservées comme référence de comportement.

**Retour :** si seule la configuration Client change, revenir à son image compatible précédente. Si les bases ont déjà divergé, repli par domaine uniquement avec le protocole post-commit ; **pas** de retour global automatique au vieux monolithe. Garder les backups protégés, sans credentials runtime qui permettraient une double écriture.

## M10 — Reconciliation (nouvelle fonctionnalité, plus tard)

**Travail futur :** service/base propres pour cas/propositions/décisions ; lecture de snapshots et candidats via APIs autorisées. Règles de mapping/propriété et permissions à approuver avant toute application à une projection Client. Aucun écrit Carthago.

**Acceptation :** tests d'isolation, liens/provenance, revue humaine, conflits/version, replay et décisions immuables. Sans politique approuvée, seules revue/simulation autorisées, commandes d'application bloquées. Aucun changement automatique d'identité/compte par publication d'un snapshot.

**Retour :** désactiver les nouvelles routes et arrêter l'application de décisions ; garder historique et snapshots. Une décision déjà appliquée exige une nouvelle décision corrective autorisée chez le propriétaire, jamais effacement ou écriture inverse Carthago.

## M11 — Reporting puis AI, lots séparés

**Reporting :** commencer après validation des formules/organisations/données ; projections propres et contrats autorisés, pas de SQL universel. **Acceptation :** résultats synthétiques de référence, filtre avant agrégation/export et révocation sur caches. **Retour :** désactiver les nouveaux indicateurs/exports et revenir aux écrans actuels sans chiffres inventés ; préserver l'historique des définitions.

**AI :** service séparé seulement avec périmètre/fournisseur/rétention approuvés. **Acceptation :** accès retrieval/citations isolé, révocation et sécurité documentaire démontrées. **Retour :** désactiver les routes/appels fournisseur, conserver ou purger les artefacts selon politique approuvée, sans altérer les dossiers métier. Ces lots ne sont pas nécessaires au checkpoint M9.

## Roadmap métier et impact attendu

| Travail | Impact attendu, sans estimation artificielle |
|---|---|
| Cette intervention | Documents seulement ; zéro modification du code métier, des routes, de Compose ou des données. |
| Gateway / contrats | Nouvelle configuration et tests ; React garde design et chemins. Quelques adaptations techniques possibles pour idempotency/corrélation/types, pas une refonte des pages. |
| Integration | Forte réutilisation parser/validation/templates/services ; adaptations ciblées des modèles distants, audit et auth ; migrations propres indispensables. |
| IAM | Plus fort risque transversal : sessions, FK, scopes, révocation, contraintes et fixtures doivent évoluer avant indépendance réelle. |
| Commercial / Client | Réutiliser validators/CRUD ; déplacer modèles/vues ciblés, remplacer jointures, orchestrer création prospect ; classification Client et sous-types restent locaux. |
| Tests | Séparer les fixtures multi-apps, conserver les tests de référence et ajouter contrats, pannes réseau, restauration et isolation DB. Les tests existants seuls ne prouvent pas une architecture distribuée. |
| Suite fonctionnelle | Agenda/rendez-vous et campagnes dans Commercial, puis Pilotage Managérial dans Reporting avec formules approuvées. Les développer par lots compatibles avec ces frontières ; ne pas mêler une extraction à une nouvelle règle métier. |

**Première étape technique recommandée après cet audit : M1, puis M2 Gateway transparent.** Ne pas déplacer Identity ou les tables maintenant. La première extraction effective sera Integration après M3/M4 ; c'est la plus petite progression vérifiable qui préserve les garanties actuelles.
