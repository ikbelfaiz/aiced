# M1 — Référence vérifiable et répétition de restauration

Implémenté et vérifié le 14 novembre 2026. Premier incrément du [plan](migration-plan.md), **avant M2 Gateway**. DRF, APIs, schéma applicatif et données existantes restent en place. Aucun service métier extrait ; aucun transfert de propriété, nouvelle migration, reset ou adaptation visuelle. La cible service-based n'est pas encore atteinte.

## Livrables et fichiers

| Fichiers | Changement |
|---|---|
| `scripts/migration_baseline.py` | Entrée M1 : environnement synthétique isolé, manifeste privé, pg_dump/pg_restore, comparaison et tests. Aucun dump ni writer sur la base existante. |
| `scripts/tests/test_migration_baseline.py` | Huit tests des garde-fous, du refus de nettoyage non autorisé et de la détection des différences. |
| `backend/testing/__init__.py`, `fixtures.py`, `rehearsal.py` | Fixtures synthétiques communes et identification fermée des bases de répétition. Pas un service ni un propriétaire de tables. |
| `backend/identity/tests.py`, `clients/tests_workspace.py`, `clients/tests_prospects.py`, `ingestion/tests.py` | Réutilisation des fixtures sans importer une autre classe TestCase ; assertions métier existantes conservées. |
| `backend/contracts/__init__.py`, `tests.py`, `public-api-baseline.json` | 38 routes/méthodes figées, 16 migrations historiques fingerprintées, six scénarios consommateurs couvrant les familles API React et les refus. Le manifeste est dans le contexte Docker backend, sans dépendance aux fichiers docs pour exécuter les tests. |
| `backend/core/management/__init__.py`, `commands/__init__.py`, `commands/migration_rehearsal_fixture.py` | Commande de test privée gardée : données synthétiques, snapshot publié, doublons/rejets, activité, estimation Decimal, lien externe fictif et session persistée ; validation après restauration. Aucun endpoint. |
| `scripts/frontend_e2e.py`, `frontend/playwright.config.ts` | Choix explicite d'un environnement de répétition validé, mot de passe synthétique privé et répertoires de rapports par run ; comportement par défaut conservé. |
| `frontend/e2e/workspace.spec.ts` | Attendre le filtre URL après recherche debounced avant clic ; le test ne dépend plus d'un portefeuille prérempli de nombreux clients. Aucun fichier `frontend/src` modifié. |
| Présent bilan, roadmap, plan et README | Commandes, preuves, portée et rollback documentés. |

Le manifeste de migrations utilise SHA-256 du texte UTF-8 avec fins de ligne normalisées LF : une conversion Windows/Linux de fins de ligne ne constitue pas une modification de migration. Les fichiers historiques n'ont pas été édités. Modifier un contenu ou une route exige une revue explicite de la référence, pas une régénération automatique pour faire passer les tests.

## Exécution

Depuis le dépôt Windows préparé, PostgreSQL local déjà disponible, dépendances Python/Node/Chromium installées :

```powershell
python -m unittest discover -s scripts/tests -v
python scripts/migration_baseline.py --confirm-synthetic
```

Le runner lit `.local/postgres/env.json` sans le modifier. `--env-file` sélectionne un autre fichier local explicite ; seuls DEBUG=1 et un hôte PostgreSQL loopback sont permis. Les clients pg_dump/pg_restore sont pris dans `.tools/pgsql/bin` ou PATH. L'utilisateur PostgreSQL doit pouvoir créer les bases de test. Le runner navigateur existant dépend du toolchain Windows local ; aucune exécution Docker ou Linux de cette répétition n'est annoncée comme vérifiée.

`--skip-browser` fournit un résultat `partial-backend-only`, **pas un gate M1 complet**. Les commandes génériques backend doivent inclure la nouvelle suite : `python manage.py test core identity clients ingestion audit contracts --noinput`.

## Isolement et sauvegarde

1. Fingerprint de la base existante dans une transaction `REPEATABLE READ READ ONLY` : comptes par table, hash des lignes triées, colonnes, FK/checks/uniques, indexes, triggers/fonctions, propriétaires/ACL des tables et séquences. Aucun contenu brut de ligne n'est écrit au manifeste ou affiché.
2. Création de deux bases **neuves**, noms `aiced_m1_<run UUID>_source` et `_restore`, chacune avec un marqueur PostgreSQL de ce run. Aucun nom de destination utilisateur n'est accepté.
3. Migrations existantes et fixtures exécutées seulement sur la source synthétique ; pg_dump custom de cette source, puis pg_restore dans la seconde base vide.
4. Comparaison intégrale des empreintes, contraintes et séquences ; test de la session sauvegardée et du workspace/version/import publié dans la copie restaurée. Le backup ne contient que les fixtures produites dans cette base neuve.
5. Neuf tentatives invalides sur la copie restaurée, toutes rollback : audit append-only, staging/snapshot immuables, affectation same-org, sous-type différé, longueur notes, unicité compte source, cohérence de publication et séparation approbateur. Nouvelle empreinte prouvant zéro effet des probes.
6. Checks Django/migrations/OpenAPI, suite backend dans sa base de test Django distincte, build frontend, puis les deux suites Chromium **sur la copie restaurée**. Ces suites effectuent réellement les saisies/imports attendus ; elles n'utilisent jamais la base applicative protégée.
7. Nouvelle empreinte de la base existante, comparaison, puis suppression des deux bases scratch dont le nom, le run et la création par ce processus sont confirmés. Refus de nettoyage si le marqueur diverge ; rapport en échec et conservation pour investigation, pas de suppression élargie/forcée.

pg_dump/reparse peut déplacer le cast constant `::text[]` vers chacun des littéraux d'un CHECK d'appartenance. Le comparateur reconnaît uniquement les deux expressions complètes équivalentes et conserve colonne/liste des valeurs. Pas de suppression générique de casts/predicates ; une valeur changée, `OR true` ou `CHECK(true)` reste une divergence bloquante. Ce cas et le nettoyage protégé sont testés.

Les artefacts privés restent sous `.local/migration-baseline/<run>/` (ignoré) : dump **synthétique**, état/session/mot de passe synthétique, environnement, empreintes, OpenAPI, logs et rapports. Ne pas les committer. Cette répétition n'est **pas une sauvegarde de production**, ne définit pas la rétention/chiffrement/RPO/RTO de production et ne donne aucune autorisation de copie/cutover de production.

## Résultats exécutés

Run complet : `309d0d5a39bc47a9a02f2fc074b945ba`, rapport privé `report.json`, statut `passed`.

| Vérification | Résultat |
|---|---|
| Garde-fous du runner | **8 tests OK** |
| Suite PostgreSQL de référence + contrats | **96 tests OK**, 52,699 s |
| Contrats après déplacement du manifeste dans le contexte backend | **6 tests OK**, 8,005 s |
| Django check / migrations dry-run / OpenAPI fail-on-warn | OK, aucune migration manquante ni erreur de schéma |
| TypeScript / bundle Vite | OK ; avertissements de commentaires Zod non bloquants |
| Chromium développement sur copie restaurée | **11 scénarios OK**, 55,5 s |
| Chromium bundle compilé sur copie restaurée | **6 scénarios OK**, 42,8 s |
| Restauration | 30 tables, mêmes données/schema/contraintes/acteurs/versions/digests/séquences ; session et historique publiés lisibles |
| Probes de contraintes sur la vraie copie restaurée | **9 rejets attendus**, aucun effet persistant |
| Base applicative existante | Empreintes avant/après identiques ; données, schéma et séquences conservés |
| Nettoyage | Les deux bases scratch du run supprimées ; aucun reset ni transfert de propriété |

Fonctions vérifiées : connexion/CSRF/session/déconnexion, rôles et refus IT/inter-objets/inter-organisations, lecture Client 360/finance autorisée seulement, création/édition CRM AICED, conflits de version, prospects/interactions/opportunités, fichiers malformés, preview/rejets, double acteur, publication snapshot-only et replay idempotent. Les vérifications du bundle ne constituent pas un déploiement de production. Aucun accès Carthago ajouté.

Problèmes corrigés pendant cette mise en place : assertion de cookie basée sur force_login remplacée par une vraie connexion HTTP ; équivalence restreinte des CHECK PostgreSQL après restore ; test navigateur rendu indépendant de l'accumulation de clients ; rapport de finalisation conservé même lors d'un refus de nettoyage. Les premiers essais en échec ont arrêté le gate et confirmé la préservation de la base existante ; ils ne sont pas comptés comme réussites.

## Rollback et suite

M1 ne change aucune donnée métier, migration historique, route ou propriété de table : revenir aux anciens tests/runners ne nécessite aucun rollback de base. Les deux bases temporaires sont déjà retirées après le run réussi. Les rapports/dumps privés peuvent être conservés suivant la politique locale ; aucune suppression récursive automatique de fichiers.

Si une exécution échoue : lire son rapport privé, garder le runtime courant. Ne pas restaurer le dump synthétique dans la base applicative. Un nettoyage refusé nécessite vérification du nom/marqueur exact ; ne pas élargir les filtres ni utiliser une suppression de toutes les bases de préfixe similaire.

**M2 Gateway transparent est le prochain incrément**, non implémenté ici. Puis journal/outbox et contrat IAM/révocation, avant le candidat Data Integration. Aucun service métier, credential inter-service ou base propriétaire extrait dans M1 ; authentification inter-services et preuves d'indépendance restent à réaliser avant toute extraction. Une sauvegarde/restauration approuvée sur le vrai périmètre de production reste un gate distinct avant tout déplacement de ses données.
