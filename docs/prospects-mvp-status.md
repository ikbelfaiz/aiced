# MVP CRM autonome — tranche prospects

Vérifié le 14 novembre 2026 sur PostgreSQL 17 local et Chromium. Architecture et ordre présentés avant modification : CRM autonome → prospects/interactions/opportunités → agenda → campagnes → pilotage managérial. Aucune dépendance à un accès Carthago de production.

## Fonctionnalités vérifiées

- Migration `clients/0006_prospect` appliquée : qualification AICED, source d'acquisition, prochaine action/date et version ; identité interne distincte des références externes.
- `GET/POST /api/prospects/`, contexte d'organisations et `GET/PATCH /api/prospects/{uuid}/` ; recherche, statut et pagination bornée. Création physique/morale et qualification manuelle transactionnelles, champs explicitement autorisés, audit et conflits 409 sur version obsolète.
- React `/prospects` : navigation habilitée, création/qualification, fiche partagée, interactions et opportunités persistantes, états chargement/vide/erreur/interdit, adaptation mobile. Montants d'opportunité Decimal conservés comme estimations commerciales, sans encours inventé.
- Les prospects sont exclus du Panorama Clients. Leur accès exige `prospects.view` et `clients.view` sur le même objet dans toutes les routes, y compris les routes historiques. Les dates d'interaction ne sont renvoyées qu'avec la permission correspondante.
- `seed_prospects --confirm-synthetic` exécuté deux fois : deux contacts de démonstration explicitement nommés et rôle prospects séparé pour l'opérateur synthétique existant. Aucun élargissement des rôles Phase 1.
- Adaptateur `SyntheticReadOnlySource` sans réseau ni méthode d'écriture ; fixture versionnée et immuable. Adaptateur réel Carthago désactivé ; snapshots publiés existants toujours isolés des identités/comptes.

## Problèmes traités

- Protection contre l'accès indirect à un prospect via un endpoint client historique : filtrage commun, pas seulement sur la nouvelle liste.
- Protection contre les mises à jour perdues et validation de cohérence action/date ; rollback de l'identité, du profil et de la qualification si l'audit échoue.
- Labels explicites dans le formulaire partagé, chevron du filtre et espacement de 24 px avant la table après comparaison visuelle.
- Contrat OpenAPI de la liste paginée explicite ; collisions de noms d'enums/statuts et d'opérations corrigées, types frontend régénérés.

## Vérifications exécutées

| Vérification | Résultat |
|---|---|
| `python scripts/backend_check.py migrate --noinput` | `clients.0006_prospect` appliquée |
| `check` et `makemigrations --check --dry-run` | Aucun problème ni migration manquante |
| `test core identity clients ingestion audit --noinput` | **90 tests OK**, 50,040 s |
| `spectacular --validate --fail-on-warn` | Aucune erreur ni avertissement |
| `npm --prefix frontend run build` | TypeScript et Vite OK |
| `python scripts/frontend_e2e.py --grep-invert 'production build'` | **11 tests Chromium OK**, 57,2 s |
| `python scripts/frontend_e2e.py --production --grep 'production build\|Client 360\|Data Management\|Prospects'` | **6 tests Chromium OK**, 39,3 s |

Les tests backend couvrent notamment refus inter-organisations et inter-objets, périmètre affecté, révocation, absence de privilège IT, champs inconnus, CSRF, validation, précision Decimal, conflits et rollback. Les régressions Client 360 et import couvrent toujours publication indépendante, rejets, doublons, idempotence et absence de fusion source. Les tests navigateur du build compilé utilisent un serveur Django de test isolé en DEBUG ; ce n'est pas une recette de déploiement production.

PDF 06 Prospects rendu et inspecté visuellement ; captures privées `.local/ui-review/06-1.png` et `screens/prospects-desktop.png`, `screens/prospects-mobile.png`. Grille/sidebar/couleurs/espacements comparés. Différences intentionnelles : contenu synthétique API, absence de scores et taux inventés, moins de filtres, pas d'export, actions réelles ajoutées ; police Inter approximative et adaptation mobile sans référence mobile. Aucune fidélité pixel exacte annoncée. Références, captures, uploads et secrets restent hors versionnement.

## Limites et prochaines tranches

- Rendez-vous/agenda, campagnes et Pilotage Managérial non implémentés dans cette tranche. La prochaine action est une indication CRM, sans rappel ni événement d'agenda automatique.
- Pas de scoring, de conversion automatique, d'affectation/réaffectation par API ou de rapprochement. Les statuts sont manuels ; règles de pilotage et matrice production à valider.
- Écritures Carthago et mises à jour d'identités/comptes/finances source toujours bloquées. Publication Excel limitée aux snapshots immuables sous contrôle de revue.
- Le contrat de démonstration de l'adaptateur n'est pas un schéma Carthago approuvé et n'alimente automatiquement aucune table métier.
- Validation navigateur limitée à Chromium ; tests de charge, déploiement TLS, séparation des comptes PostgreSQL migration/runtime et recette métier production restent à mener. Avertissements de commentaires d'annotation Zod pendant Vite, sans échec de compilation.
