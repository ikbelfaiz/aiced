# État courant après S7/S8

L'architecture est gelée à quatre services Django — IAM, Client & CRM,
Commercial, Data Integration — derrière Nginx et React, avec les schémas et
credentials restreints existants. Les interactions et prospects restent chez
Client & CRM ; les opportunités restent chez Commercial. Les prochains
incréments ajoutent des fonctions dans ces frontières, sans extraction ni
transfert de tables. Voir [S8](migration/s8-functional-validation.md) et
[Compose courant](docker-compose.md). Le texte antérieur ci-dessous conserve
les décisions initiales, remplacées par cette cible lorsqu'elles divergent.

---

# Architecture AICED — état actuel et cible par services

> Current architecture: **S6b verified locally**. IAM, Client & CRM, Commercial and Data Integration run separately with restricted data ownership. All 38 routes are preserved; actual post-write rollback/forward, browser workflows and restore were verified. See [S6b report](migration/s6b-commercial.md). Container execution and production readiness remain unverified. Earlier phase status paragraphs below are historical.


**Current status: S5 (2026-11-14).** IAM and Data Integration are independently running in the local synthetic deployment with separate restricted schemas/credentials. All 38 public routes are preserved. Post-write rollback, forward cutover, restore and independent IAM restart were verified. Client/CRM and Commercial remain in the compatibility backend. See [S5 results, startup and rollback](migration/s5-iam.md) and [actual ownership](migration/s5-inventory.json). Docker and production deployment are not verified. Earlier status statements below are historical.

Statut après S2 : [contrats privés signés, barrière transactionnelle de révocation et audit/outbox vérifiés](migration/s2-authorization-audit.md). Les quatre services métier restent la cible ; aucun service extrait ni changement des 38 routes. Trois tables techniques additives, deux migrations et le listener interne distinct sont en place ; le runtime public reste transitoirement le backend existant.

**Direction actualisee : quatre services Django/DRF larges (IAM, Client & CRM, Commercial, Integration), schemas/credentials separes sur PostgreSQL partage.** Voir [le plan courant et S1](migration/coarse-services-plan.md). Le monolithe actuel est transitoire ; les anciennes recommandations M2 de le conserver comme cible finale sont remplacees. Aucun service metier independant encore livre dans S1.

## Décision prioritaire : migration vers des services indépendants

La dernière demande utilisateur remplace la décision de monolithe comme architecture finale, y compris la phrase correspondante d'AGENTS.md. Le monolithe reste **l'implémentation transitoire à préserver**, pas la cible. S1 prépare les frontières sans déplacer de table ou d'API.

Cible actuelle : **Identity & Access, Client & CRM, Commercial et Data Integration indépendants**, Django/DRF conservé, une instance/base PostgreSQL avec quatre schémas et des credentials séparés. Prospects et interactions restent dans Client & CRM ; opportunités et futurs rendez-vous/campagnes dans Commercial. Analytics et Audit restent des modules bornés. Le [plan courant](migration/coarse-services-plan.md) définit les dépendances, API, migrations et gates ; le [Gateway M2](migration/m2-gateway.md) reste réutilisé. Carthago reste strictement read-only. Aucun des quatre services métier n'est encore extrait dans S1.

Documents de référence pour la migration : [état vérifié](migration/current-architecture.md), [cible](migration/target-architecture.md), [frontières](migration/service-boundaries.md), [données et relations](migration/database-ownership.md), [étapes et rollback](migration/migration-plan.md), [risques](migration/risks.md). La [roadmap actualisée](implementation-plan.md) distingue fonctionnalités présentes et futures. La garantie de révocation concurrente, la création atomique actuelle de prospect et l'audit transactionnel sont des gates de migration, pas des détails facultatifs.

## Historique de l'architecture monolithique (cible remplacée)

Les descriptions ci-dessous expliquent le socle et ses phases ; elles ne sont plus la prescription de déploiement futur. Les statuts historiques ne doivent pas contredire l'inventaire de code du nouvel audit.

Extension livrée après les trois premiers écrans : Client 360° et Gestion des données, services `clients/workspace.py` et `ingestion/services.py`, modèles de commerce et snapshots source immuables. Aucune publication vers Party/FinancialAccount ni connexion automatique Carthago. Le statut actuel et ses vérifications sont dans `client-360-data-management-status.md` ; les limites Phase 1 ci-dessous sont historiques.

Statut : architecture proposée, socle et fondations sécurité de Phase 1 implémentés. Phase frontend suivante : Connexion, Tableau de bord et Panorama Clients ajoutés sur les API existantes, avec recherche/pagination bornée et sans calcul financier ou intégration source. Les sources et leurs limites sont recensées dans `reference-analysis.md` et `open-questions.md`. Vérifications : `phase-1-status.md` et `frontend-phase-status.md`. Les mentions de frontend absent dans la description Phase 1 ci-dessous décrivent sa limite historique.

## CRM autonome — décision du 14 novembre 2026

L'absence de politique Carthago ne bloque pas le CRM autonome. PostgreSQL local reste la base AICED ; les adaptateurs source sont remplaçables et strictement en lecture seule. `SyntheticReadOnlySource` fournit un contrat de démonstration explicite, sans supposer un schéma Carthago. Les snapshots Excel publiés restent immuables et isolés ; aucun rapprochement ou changement des identités, comptes et finances source n'est autorisé.

Première tranche commerciale : `Prospect` étend une `Party` AICED avec source du contact, statut manuel, prochaine action/date et version optimiste. Interactions et opportunités existantes utilisent la même identité interne. Les prospects sont exclus du répertoire clients ; toutes les voies de lecture/écriture héritent du périmètre `prospects.view` en plus des capacités métier. L'API ne permet ni rattachement à une identité source existante, ni conversion en client Carthago. Agenda, campagnes puis pilotage suivront par tranches ; aucune formule de score ou de conversion n'est déduite des maquettes.

## Décisions
Monolithe modulaire Django/DRF et PostgreSQL, client React/TypeScript/Vite. Le navigateur communique avec `/api/` sur la même origine ; Vite relaie ces chemins en développement. Sessions Django côté serveur, cookies HttpOnly, CSRF sur les mutations. Pas de jeton durable dans localStorage. Aucun service Carthago nécessaire au fonctionnement du CRM.

Modules cibles : `identity` (utilisateurs, habilitations, organisations), `clients` (tiers et profils CRM), `commercial` (prospects, opportunités, interactions, agenda, campagnes), `reporting`, `ingestion`, `reconciliation`, `audit`, `assistance`. Une couche service porte les transitions métier et transactions ; les vues ne contournent jamais les politiques de périmètre. Phase 1 ajoute identity/policies, identity/services, clients/services et audit aux contrats ingestion désactivés. Les seules surfaces clients sont la lecture bornée, les comptes locaux en lecture seule et une mutation de notes CRM, nécessaires à la vérification des frontières de sécurité ; pas de pages frontend métier.

Les adaptateurs de sources produisent des enregistrements typés vers le même pipeline de validation et de rapprochement. Aucune capacité d'écriture externe dans leurs interfaces. Les données financières source sont séparées des données commerciales éditables. Aucun SDK IA ni traitement prédictif dans cette phase.

## Flux
Navigateur → contrôle session/CSRF → permission explicite → queryset limité au périmètre → validation → service transactionnel → PostgreSQL et audit. Le périmètre est réappliqué lors de toute lecture indirecte (export, recherche, rapport, pièce jointe, contexte IA).

Fichiers privés hors racine web, quotas et analyse des contenus avant parsing. Les documents de référence et extractions restent ignorés par Git. Les journaux opérationnels ne contiennent ni corps de requêtes ni données client.

## Exploitation
Compose local : PostgreSQL, backend et frontend. Aucun mot de passe codé dans les images. Migrations explicites avant démarrage, endpoint de vie minimal distinct de la disponibilité des dépendances. Production : TLS au proxy, cookies sécurisés, DEBUG désactivé, rotation des secrets, sauvegarde/restauration testée, stockage privé et contrôle de déploiement. Le serveur de développement ne constitue pas une configuration de production.

Les autorisations doivent être mises en place avant les endpoints métier. Les traitements synchrones bornés suffisent initialement ; une file de tâches ne sera ajoutée que si des mesures de charge le justifient.
