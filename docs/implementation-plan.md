# Roadmap AICED — migration par services et suite métier

**Current status ? S4, 2026-11-14:** Data Integration is independently running and active on the local synthetic deployment, with its own restricted PostgreSQL schema. All 38 public routes remain compatible. Forward cutover, post-write rollback, restore and independent process restart were verified. IAM, Client/CRM and Commercial are not yet independently extracted. Docker/production deployment remains unverified. See [S4 results and operations](migration/s4-cutover.md) and [verified ownership inventory](migration/s4-inventory.json). Earlier status statements below are historical.

**S2 livré et vérifié** : [autorisation interne, coordination de révocation, audit transactionnel et gates S3](migration/s2-authorization-audit.md). Prochaine extraction : Data Integration candidat synthétique, uniquement après ses migrations/settings/credentials et adaptateurs HTTP propres. Aucun service métier encore extrait ; S2 a ajouté trois tables techniques et deux migrations, sans transfert métier.

**Direction actualisee : quatre services Django/DRF larges (IAM, Client & CRM, Commercial, Integration), schemas/credentials separes sur PostgreSQL partage.** Voir [le plan courant et S1](migration/coarse-services-plan.md). Le monolithe actuel est transitoire ; les anciennes recommandations M2 de le conserver comme cible finale sont remplacees. Aucun service metier independant encore livre dans S1.

Avancement : M1 et M2 verifies ; S1 prepare les nouvelles frontieres sans extraction. Le [plan courant](migration/coarse-services-plan.md) contient les resultats, les gates et les rollbacks S1-S7. Les lots M0-M11 ci-dessous decrivent le plan historique ; leur ordre et le checkpoint a quatre bases ne font plus foi.

## Ordre courant

| Lot | Travail |
|---|---|
| S1 livre | Scoping Client hors IAM, inventaire et preuve isolee schemas/credentials |
| S2 prochain | Contrats IAM/Client HTTP, barriere de revocation testee, audit local transactionnel |
| S3-S4 | Integration independant en candidat synthetique, puis cutover approuve |
| S5 | IAM independant, sessions/CSRF/grants preserves |
| S6 | Commercial : Opportunity puis workflows approuves |
| S7 | Residu Client & CRM avec donnees et migrations propres |

Aucune extraction avant dependencies/API/barrieres operationnelles. Une instance/base PostgreSQL, quatre schemas prives ; Analytics et Audit restent des modules bornes.

## État réel à conserver

Socle Django/DRF/PostgreSQL, sessions/CSRF, rôles/scopes et audit ; Connexion, Tableau de bord et Panorama Clients ; Client 360 avec clients AICED manuels et CRM ; prospects/interactions/opportunités ; import XLSX validé, preview/rejets et publication de snapshots immuables. Voir [l'audit de code](migration/current-architecture.md), [Client 360/import](client-360-data-management-status.md) et [prospects](prospects-mvp-status.md).

« Phase 4 » est le jalon déclaré par l'utilisateur ; il ne signifie pas qu'un rapprochement opérationnel existe. Agenda, campagnes, rapprochement, reporting métier et IA ne sont pas implémentés. Aucun reset/réécriture n'est nécessaire pour corriger la cible.

## Historique : anciens lots M0-M11 (remplaces par S1-S7)

Les critères complets, dépendances, sauvegardes et retours sont dans [migration-plan](migration/migration-plan.md).

| Lot | Livrable | Gate principal |
|---|---|---|
| M0 — Audit présent | Six documents migration, tables/FK/transactions, cible et risques | Documentation seulement ; aucune extraction déclarée opérationnelle |
| M1 — Référence / restauration | Contrats consommateurs, jeux synthétiques, sauvegarde approuvée et restore isolé | Données/contraintes/audit/sessions identiques ; suites à réexécuter dans environnement autorisé |
| M2 — Gateway transparent | Même origine et mêmes routes vers backend historique | Session/CSRF/IP/TLS, limites upload, erreurs et contrat React inchangés |
| M3 — Audit / outbox | Journal transactionnel local, livraison HTTP idempotente | Rollback local, crash/replay, visibilité audit et permissions vérifiés |
| M4 — Contrat IAM / scopes | Principal vérifiable, grants, références et barrière de révocation | Équivalence du test d'écriture en attente après révocation |
| M5 — Integration candidat | DRF extrait, base/migrations/role/tests propres, shadow synthétique | Aucun accès DB voisin ; parsing/publication/security isolés testés |
| M6 — Integration actif | Copie contrôlée + writer unique + routes imports | UUID/digests/historique/replay identiques ; rollback post-commit éprouvé |
| M7 — IAM indépendant | Base et déploiement IAM, sessions/grants/audit historique préservés | Aucun accès SQL IAM distant ; révocation et sessions existantes valides |
| M8 — Commercial indépendant | Prospect/Interaction/Opportunity, références Client et orchestration | Pas de prospect actif orphelin ; compteurs/objets autorisés ; routes conservées |
| M9 — Client résiduel | Client propre et checkpoint MVP à quatre services | Déploiements/migrations indépendants, isolation DB et contrats N/N-1 |

Minimum viable pour les fonctions présentes : **API Gateway + Identity & Access + Client + Commercial + Data Integration**, chacun propriétaire de ses données. Gateway + historique + Integration est une transition utile, pas la clôture de cet objectif. Pas de services vides pour Reconciliation/Reporting/AI.

## Axe fonctionnalités : progression autonome

| Suite | Propriétaire cible | Conditions |
|---|---|---|
| Rendez-vous/agenda/rappels | Commercial | Règles temporelles/affectation explicites, scopes/historique/tests et PDF inspecté |
| Campagnes | Commercial | Accès objets avant ciblage/count/envoi/export ; aucun envoi externe non autorisé |
| Acquisition automatique read-only | Data Integration | Contrat d'accès approuvé, adapter remplaçable, validation/staging/revue/snapshots et reprise idempotente |
| M10 — Rapprochement | Reconciliation, base propre | Mapping/propriété approuvés, décisions/revue, commandes aux propriétaires seulement ; aucun écrit Carthago |
| M11a — Pilotage/KPI | Reporting, projections propres | Formules validées, jeux synthétiques de référence, filtrage avant agrégats, fraîcheur/révocation |
| M11b — Assistance documentaire/IA | AI, index propres | Périmètre/fournisseur/rétention approuvés, retrieval/citations autorisés et tests anti-fuite |
| Exploitation/préproduction | Chaque service + Gateway | Serveurs/TLS/secrets/roles DB, backups/restauration, charge, audit/alertes et recette |

Séparer extraction et nouvelles règles métier dans des lots distincts. Le CRM peut progresser dans ses frontières cibles ; l'absence de mapping Carthago bloque seulement les opérations correspondantes. La publication actuelle reste snapshot-only.

**Prochaine étape recommandée après M2 : poursuivre le MVP fonctionnel et préparer son exploitation**, sans extraction automatique. Data Integration reste le premier candidat éventuel, après justification du besoin et validation des gates sécurité/audit. Aucune copie de production ou validation distribuée annoncée.

## Ancien backlog — historique, remplacé pour la planification

Les statuts et numéros ci-dessous documentent les phases initiales ; notamment les mentions « Client 360 absent » ne décrivent plus le code courant. Se référer à l'état audité ci-dessus.

14 novembre 2026 : décision CRM autonome confirmée ; première tranche commerciale prospects → interactions → opportunités implémentée. Modèle PostgreSQL `Prospect`, API scoped et route React `/prospects`, fixtures synthétiques explicites. Voir `prospects-mvp-status.md` pour la vérification et les limites. Ordre suivant : agenda/rendez-vous, campagnes puis pilotage managérial avec règles approuvées. La dépendance Carthago bloque seulement les écritures/rapprochements source et les fonctions exigeant un contrat non approuvé.

Mise à jour : Client 360° (saisie AICED, profils, interactions, opportunités) et import Excel sécurisé avec staging/publication de snapshots livrés dans la phase `client-360-data-management-status.md`. La publication vers identités/comptes, le rapprochement, l'agenda et les calculs source restent bloqués ou hors périmètre ; les descriptions de phases ci-dessous ne valent pas déclaration de clôture complète.

Chaque phase produit une modification révisable, ses tests et un bilan. Le premier livrable se limite aux documents et au socle.

État courant : socle Phase 0 et implémentation technique Phase 1 livrés et vérifiés sur PostgreSQL. Connexion, Tableau de bord et Panorama Clients implémentés et comparés aux PDF dans une phase frontend distincte (`frontend-phase-status.md`). Cela ne clôt pas la Phase 2 : saisie et Client 360 complet absents. La matrice métier définitive et la recette de production demeurent à valider. Carthago non démarré.

| Phase | Objectif et livrables | Critères d'acceptation |
|---|---|---|
| 0 — Analyse et socle | Documents, conventions, Django/React, Compose PostgreSQL, migration User, contrat ingestion désactivé | Check Django, migration cohérente, tests refus anonyme/contrat source, build TypeScript, démarrage Compose quand outils disponibles ; limites signalées |
| 1 — Sécurité | Connexion/déconnexion CSRF, rate limiting, rôles/périmètres, audit, révocation | Matrice approuvée ; tests inter-organisations, IDs forgés, utilisateur IT, CSRF et audit ; aucun rôle implicite |
| 2 — Clients CRM | Parties/sous-types, profils, affectations, directory et 360 sans finance inventée | Contraintes et accès objet testés ; saisie manuelle validée ; écrans comparés aux PDF disponibles |
| 3 — Staging Excel | Trois modèles versionnés, upload sûr, preview et rejets privés | Tests fichiers malformés/bombes ZIP/formules/en-têtes doublés/dates ; aucun effet sur clients avant publication |
| 4 — Rapprochement/publication | Cas, propositions, approbation, propriété, transaction/idempotence | Politique approuvée ; replay/concurrence/rollback testés ; aucune fusion incertaine ; aucune suppression par absence ; aucun accès sortant d'écriture |
| 5 — Commerce | Prospects, opportunités, interactions, agenda/rappels, campagnes | Transitions et affectations validées ; permissions bulk et historique testés ; UI accessible |
| 6 — Pilotage | KPI, filtres, rapports, segmentation et engagement validés | Formules approuvées et jeux synthétiques de référence ; agrégats respectant périmètre ; aucun scoring non défini |
| 7 — Assistance | Recherche documentaire autorisée puis résumés et recommandations | Fournisseur/rétention approuvés ; isolation retrieval testée ; citations et absence de réponse explicites ; pas de prédictions inventées |
| 8 — Préproduction | Durcissement, observabilité, restauration, charge, recette | Revue sécurité, restore réel, TLS/secrets, tests E2E et recette métier/visuelle ; résolution des bloqueurs |

Ne pas démarrer une intégration automatique avant contrat approuvé. Les maquettes manquantes bloquent la recette visuelle, pas la préparation du backend. Les règles financières et autorisations manquantes bloquent les comportements correspondants.
