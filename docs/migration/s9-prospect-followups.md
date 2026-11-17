# S9 — Relances prospects

## Périmètre et contrat

La route frontend `/prospects/relances` ouvre une liste dédiée via la navigation
« Relances prospects ». « Qualifier les prospects » réutilise la liste et son
éditeur existants. Chaque ligne ouvre la fiche Client 360 du prospect.

Le service Client & CRM expose uniquement une lecture additive :
`GET /api/prospects/follow-ups/`. Aucun autre contrat public n'est modifié.
Les 38 routes historiques et leurs schémas restent figés ; l'historique S8 et
la worklist S9 donnent 40 routes publiques, 49 couples méthode/route.

Paramètres : `search` (nom, source du contact, prochaine action, 200 caractères),
`status` (`contact`, `qualified`, `discussion`, `follow_up`, `closed`),
`bucket` (`overdue`, `today`, `upcoming`, `unscheduled`), `date_from`, `date_to`
(ISO, bornes inclusives), `ordering` (`next_action_date`, `-next_action_date`,
`display_name`, `-display_name`), `page`, `page_size` (1–50, défaut 8).
Une plage inversée ou un filtre invalide renvoie 400, une page inexistante 404.
Les égalités de tri sont départagées par UUID ; les dates absentes viennent
en dernier dans les deux sens du tri par date.

La réponse conserve l'enveloppe paginée habituelle et les lignes Prospect
existantes ; elle ajoute `business_date`, `business_timezone` et `buckets`.
Les compteurs portent sur les objets autorisés après recherche/statut/bornes,
avant sélection d'une échéance. `count` porte sur la sélection finale.

## Dates et règles explicites

La date de référence vient de l'instant courant converti avec la base IANA
`Africa/Tunis`, indépendamment du fuseau serveur et du navigateur. Une date
de prochaine action est une date calendaire, sans conversion d'instant :
avant la date métier = retard ; égale = aujourd'hui ; après = à venir ;
NULL = sans date, y compris si aucune action n'est renseignée. Les bornes de
dates excluent les NULL. Tous les statuts, dont Clos, sont inclus par défaut :
aucune exclusion ou clôture automatique n'est inventée. Le statut est filtrable.

L'interface affiche la date métier fournie par le serveur et actualise la
requête chaque minute et au retour du focus. Aucune notification ni garantie
temps réel n'est introduite. Une erreur masque lignes et compteurs, y compris
si un résultat précédent existe dans le cache.

## Sécurité et architecture

`prospect_queryset` applique l'intersection des droits `clients.view` et
`prospects.view` sur le même objet avant filtres, agrégats et pagination.
Les scopes assigné/organisation et les exclusions prospect existantes restent
actifs. Anonyme/IT sans ces droits : 403. L'IAM reste l'autorité distante,
avec session et révocation existantes ; aucune copie de propriété, écriture
CRM/source, finance, calendrier ou service supplémentaire.

Aucune migration ni changement Compose. Les mutations de qualification
continuent de passer par les services existants versionnés, coordonnés avec
la révocation, audit et outbox transactionnels. Carthago reste en lecture seule.
Tous les nouveaux jeux sont explicitement synthétiques.

## Reproduire la validation

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/followups.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_browser.py --test
python scripts/compose_followups_restart.py --test
python scripts/compose_validate.py
python scripts/compose_inventory.py --test
```

Exécuter les sondes qui modifient temporairement les habilitations séparément
des suites navigateur. Aucun processus local ne sert l'application pendant
ces tests. Les rapports privés restent dans `.local/compose-test/`.

Le script de vérification audit S7 comparait un total global de reçus entre
deux livraisons limitées à 100 événements. Sur une base synthétique réutilisée,
d'autres événements en attente peuvent légitimement être livrés. Il vérifie
désormais l'unicité du reçu de l'événement précisément rejoué et sa nouvelle
confirmation de livraison ; aucune règle métier ou livraison n'est modifiée.

## Résultats du 15 novembre 2026

Docker Engine **29.9.3**, Compose **v5.7.0**, réellement disponibles.
Reconstruction de l'application compilée avec TypeScript/Vite réussie.
Sept conteneurs sains dans `aiced-test` : PostgreSQL, IAM, Client, Commercial,
Integration, frontend, gateway ; initialisation terminée avec code 0.
L'inventaire confirme quatre processus Django distincts, DNS interne,
credentials propres et seul le port gateway publié. URL test :
`http://127.0.0.1:5188/prospects/relances`.

| Vérification exécutée | Résultat final |
|---|---|
| Régression backend Client/core/identity/ingestion/audit/internal/contracts/architecture/gateway | 151 tests réussis, dont 6 nouveaux tests S9 |
| Suites propres IAM / Integration / Commercial | 5 / 8 / 5 réussis ; total backend 169, aucun échec |
| Chromium, frontend compilé via Nginx et vrais services | 17 réussis, 1 ignoré car réservé aux maquettes en mode développement ; aucun échec final |
| Nouveaux scénarios navigateur S9 | 3 réussis : qualification réelle puis worklist/filtres/tri/pages/fiche/mobile ; IT refusé ; erreur/reprise sans données en cache affichées |
| Fuseau navigateur S9 | America/Los_Angeles ; date métier et filtres fournis par Africa/Tunis |
| Autorisations réelles IAM + Nginx S9 | 3 contrôles réussis : assignation avant compteurs/pages, intersection sur même objet, révocation immédiate |
| Vérification quatre services existante | 15 contrôles réussis : restrictions SQL/historiques, contrats, concurrence/révocation, signatures/rejeu, rollback audit/outbox, livraison dédupliquée et lecture audit fédérée |
| Routes publiques sans authentification | 40 routes / 49 couples méthode-route vérifiés, routes retirées refusées |
| Redémarrage réel du seul conteneur Client | Même session, lignes/compte/compteurs identiques ; nouveau processus Client, trois pairs inchangés |
| Compose | 8 configurations historiques/renommées équivalentes ; projet/volume/credentials test distincts |
| Migrations et travail Git | `makemigrations --check --dry-run` : aucun changement ; `migrate --check` et `git diff --check` réussis |

Les six tests backend couvrent notamment minuit UTC/Tunis, bornes inclusives,
dates NULL avec/sans action, statut Clos, filtres invalides, pagination/tri
stable et droits assignés/inter-organisations. Ils ont été exécutés avant
l'endpoint et échouaient alors en 404. Une assertion initiale du test de
lecture seule a été corrigée pour envoyer du JSON et attendre 405.

Une relance navigateur ciblée a croisé les sondes qui désactivent
temporairement les droits de l'opérateur : un scénario a expiré. La suite
complète finale a été exécutée après les sondes et passe séquentiellement.
Le défaut du script de contrôle audit décrit plus haut a aussi été corrigé
et son contrôle complet relancé avec succès. Les erreurs réseau injectées
par Playwright vérifient l'interface ; elles ne constituent pas une preuve
d'arrêt physique de l'IAM. Aucun nouvel exercice complet sauvegarde/restauration
ou panne PostgreSQL n'est revendiqué pour S9 ; ceux de S7/S8 restent historiques.

## Fichiers de cet incrément

- Backend : `backend/clients/followups.py`, `backend/clients/tests_followups.py`,
  `backend/config/urls.py`, `backend/contracts/additions.py`.
- Frontend : `frontend/src/features/prospects/ProspectFollowups.tsx`,
  `frontend/src/app/App.tsx`, `frontend/src/components/layout/AppShell.tsx`,
  `frontend/e2e/followups.spec.ts`.
- Validation Docker : `infra/acceptance/followups.py`,
  `infra/acceptance/verify.py`, `scripts/compose_followups_restart.py`.
- Documentation : ce rapport, `docs/functional-gap-analysis.md`,
  `docs/mvp-backlog.md`.

Les modifications S7/S8 déjà présentes dans l'espace de travail sont conservées.
Aucun fichier Compose, Dockerfile, secret ni migration n'est modifié par S9.

## Limites et suite

Pas d'agenda, campagne, rappel automatique, relance des clients sans prospect,
ni nouvelle règle de score. Les dates restent déclaratives et peuvent être
absentes. L'édition reste dans la liste des prospects, pas dans la worklist.
Les décisions AMEN INVEST sur calendrier, notifications, résultats de contact,
KPI et données Carthago restent ouvertes dans `open-questions.md`.

Prochain incrément recommandé : PAN-01, filtres profession/secteur CRM
déclarés, sans segmentation inférée. Les limites de déploiement S7/S8
(HTTP de démonstration, serveur de développement/preview, exploitation des
secrets/certificats et livraison outbox) demeurent ; ces tests ne démontrent
pas une aptitude à la production.
