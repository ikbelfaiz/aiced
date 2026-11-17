# S13 — Pipeline : volume et autorisation

## Cause et choix

S11 collectait jusqu'à 501 dossiers distincts présents dans Commercial, avant
filtrage Client. Une grande population invisible pouvait donc provoquer un 503
pour un petit portefeuille autorisé. Le plafond bornait un dictionnaire Python
global ; le relever n'aurait pas corrigé cette dépendance.

Le plan S12 a été évalué dans les frontières existantes. Le runtime Commercial
n'a pas le privilège PostgreSQL TEMP : aucune permission n'a été ajoutée. Une
table temporaire a donc été écartée. L'énumération Client puis une fusion de
top-K en mémoire aurait fait dépendre la mémoire de l'offset public, ou nécessité
plusieurs parcours. Le choix est un **curseur PostgreSQL Commercial ordonné**,
avec décisions Client par lots, compteurs et conservation de la seule page.
Ce parcours reste linéaire, sans liste globale d'IDs ni cache d'autorisation.

Le premier prototype utilisait le contrat S11 par lots de 100 : 4,92–5,59 s à
10 000 lignes, 105 appels Commercial sortants. Il a été écarté car une lecture
pouvait dépasser le délai d'attente de révocation de 5 s. Le contrat compact
borné ci-dessous réduit ce coût sans modifier les propriétaires ou privilèges.

## Garanties et contrats

- `/api/opportunities/`, filtres, sérialisation, liens, statuts, Decimal,
  pagination et OpenAPI publics restent inchangés. Aucun changement d'interface.
- Nouveau POST **privé uniquement**
  `/internal/v1/clients/opportunity-scope-batch` : credentials IAM existants,
  `party_ids` (maximum 500), `search` (maximum 200). Réponse : `actor_id`,
  `scope_revision`, objets autorisés `{id, name_match}`. La correspondance du
  nom est calculée par Client avec le casefold existant. Aucun identifiant
  n'est accepté comme preuve d'accès ; intersection clients/opportunités et
  visibilité prospect identiques au contrat S11. HMAC, audience et anti-rejeu
  existants ; enveloppe HTTP toujours limitée à 64 KiB.
- L'ancien endpoint privé, toujours borné à 100, conserve ses champs. Il ajoute
  `scope_revision`, marqueur opaque de cohérence des droits IAM effectifs.
  Ce marqueur ne donne aucun droit et ne peut être réutilisé pour éviter IAM.
- Commercial lit 500 opportunités par FETCH du curseur serveur, dans un snapshot
  REPEATABLE READ, avec tri existant NULLS LAST et UUID de départage. Il autorise
  chaque lot avant recherche, comptes, statut et offset. Les titres/notes gardent
  le `icontains` PostgreSQL existant ; les noms restent évalués par Client.
- Seuls les objets de la page (maximum 50) sont conservés. Leurs noms et droits
  d'édition sont relus via le contrat S11, sous le même marqueur. Une plage
  Python `range(count)` conserve la pagination DRF et les erreurs de page sans
  allouer une liste de taille `count` ou `offset`.
- Les barrières partagées IAM/Client existantes sont acquises sans attente :
  une mutation en cours ou en attente provoque un 503 sans données. Les RPC
  lecteurs restent sans verrou. Les mutations exclusives attendent la lecture
  admise ; le budget de traitement de **4 s** reste sous leur attente de 5 s.
  Il n'y a aucun changement de politique des mutations IAM/Client.
- Chaque RPC conserve son plafond de 3 s, réduit au temps restant. Chaque FETCH
  SQL reçoit le budget restant ; work_mem local vaut 4 MiB. Le budget global
  est vérifié entre lots et avant réponse. Un dépassement ferme l'accès sans
  résultat partiel. Le gate Commercial garde son attente existante bornée ;
  une attente préalable peut consommer le budget et conduire à un 503.
- IAM et Client sont relus en fin de parcours. Le marqueur détecte aussi une
  expiration temporelle de droit, qui ne prend pas de verrou. Une identité,
  signature, réponse ou décision incohérente ferme l'accès. Aucun cache durable,
  table, migration, credential, service ou journal métier supplémentaire.

Déploiement compatible : mettre Client à jour avant Commercial, puis redémarrer
le gateway après recréation des conteneurs (résolution DNS Nginx existante).
Une version Client ancienne ne provoque jamais de fallback : le nouveau
Commercial échoue sans exposer de données.

## Mesures Docker réelles, 15 novembre 2026

Docker Engine 29.9.3, Compose v5.7.0, projet isolé `aiced-test`, PostgreSQL privé
marqué synthétique. Les tailles ci-dessous désignent des opportunités de test
distinctes sur autant de dossiers de l'organisation B. Il existait aussi
80 opportunités / 39 dossiers synthétiques d'autres recettes. Aucun import réel.
La colonne dossiers inclut ce fond existant ; maximum testé : **10 080
opportunités, 10 039 dossiers distincts, dont 10 000 autorisés**.

Chaque latence Nginx est la médiane de trois requêtes séquentielles, avec
recherche `S13-SYNTHETIC`, tri titre et page de 50. Ce n'est pas un p95 de charge.

| Jeu ajouté | Dossiers totaux | Avant : code / médiane s | Après : code / médiane s | SQL Commercial avant → après | HTTP Commercial avant → après | FETCH après |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 139 | 200 / 0,3934 | 200 / 0,2375 | 9 → 11 | 5 → 6 | 2 |
| 500 | 539 | 503 / 0,1546 | 200 / 0,3050 | 4 → 12 | 2 → 7 | 3 |
| 1 000 | 1 039 | 503 / 0,1781 | 200 / 0,3553 | 4 → 13 | 2 → 8 | 4 |
| 5 000 | 5 039 | 503 / 0,2368 | 200 / 0,8295 | 4 → 21 | 2 → 16 | 12 |
| 10 000 | 10 039 | 503 / 0,1916 | 200 / 1,4615 | 4 → 31 | 2 → 26 | 22 |

Les refus rapides avant ne constituent pas des lectures réussies comparables.
SQL et HTTP sont instrumentés dans un worker Docker utilisant le code
Commercial, son credential restreint, la vraie base et les vrais pairs HTTPS.
SQL compte les exécutions Django, hors BEGIN/COMMIT/CLOSE ; les FETCH du curseur
sont comptés séparément. Les SQL Client/IAM ne sont pas instrumentés : aucune
prétention de total SQL de toute l'application. Le worker instrumenté prend
2,277 s au maximum ; les latences du tableau passent réellement par Nginx.

Avant : pic d'allocations Python 3 354 817 octets, RSS worker 69 836–70 088 KiB.
Après : 3 372 932 octets à toutes les tailles ; RSS worker 69 544–71 140 KiB.
Ces mesures incluent l'amorçage Django et des notes synthétiques courtes ; elles
ne sont pas une garantie de mémoire avec des notes maximales ou plusieurs lecteurs.
Une requête Nginx supplémentaire à 10 000 a mesuré 1,654 s et des échantillons
RSS du **processus Django Commercial** à 74 308–74 312 KiB. Ses logs réseau
confirment 24 appels Client + 26 snapshots IAM = **50 HTTP internes**, dont les
24 appels Client→IAM, absents du compteur Commercial du tableau. Le PID init
du conteneur n'est pas utilisé pour cette mesure.

Rapports détaillés exclus : `.local/compose-test/pipeline-scale-before.json`,
`pipeline-scale-after.json`, `pipeline-http-metrics.json`,
`pipeline-scale-verification.json`, journaux de régression et navigateur.

## Reproduction et validation

Le benchmark est destructif **uniquement pour ses propres opportunités
synthétiques identifiées**, dans la base jetable vérifiée par nom et marqueur.
Il conserve les dossiers/références immuables et l'historique d'audit. Ne pas
lancer les révocations/pannes pendant les tests navigateur ou les mesures.
Le baseline « before » a été capturé avant modification ; le rejouer sur S13
ne reconstitue pas l'ancien code et ne doit pas écraser sa preuve historique.

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/pipeline_scale.py after
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/pipeline_scale_verify.py
python scripts/compose_pipeline_metrics.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
$env:AICED_E2E_SCALE='1'
try { python scripts/compose_browser.py --test } finally { Remove-Item Env:AICED_E2E_SCALE }
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/pipeline.py
python scripts/compose_pipeline_recovery.py --test
python scripts/compose_inventory.py --test
python scripts/compose_validate.py
```

La régression backend finale passe : **193 tests**, dont 168 socle/Client/
contrats, 5 IAM, 8 Integration et 12 Commercial. Un premier test synthétique
de 500 personnes omettait leurs sous-types obligatoires : cette fixture a été
corrigée, puis les quatre suites ont été relancées avec succès.

Les **12 contrôles grand volume** passent : oracle à 10 000, pages et statuts,
recherche nom seul, dates nulles/égalités, révocation réelle, barrières IAM et
Client, refus de nouveaux lecteurs pendant mutation, PATCH concurrent avec
snapshot puis relecture fraîche, stale 409, paires audit/outbox exactes,
expiration pendant parcours, timeout HTTPS réel à budget artificiellement
court, signatures invalides, mauvais chemin signé et rejeu via TLS réel.
Les écrivains exclusifs synthétiques utilisent les mêmes barrières que les
mutations et le délai existant de 5 s ; leurs attentes mesurées sont
**IAM 1,5777 s / Client 1,4811 s**. Ils modifient directement les fixtures sous
transaction admin ; les mutations applicatives réelles sont couvertes par les
probes gateway existantes, distinctes de cette orchestration de course.

La suite Chromium compilée finale passe : **25 scénarios réussis, 1 ignoré**
(captures réservées au mode développement). Le nouveau scénario volume est
bien activé et réussi ; il ne fait pas partie des ignorés. Deux courses du
runner ont été corrigées : attendre la fin du login avant une navigation,
puis le filtre réellement appliqué avant tri/page et statut avant reload.
Les comptes attendus n'ont pas été assouplis. La suite complète a été relancée.

Les **15 probes d'intégration** existantes passent, dont isolation SQL sous les
quatre vrais credentials, historiques de migration, révocation/affectation,
atomicité audit/outbox et déduplication. Les **5 probes pipeline** passent aussi
alors que la grande population de l'autre organisation est toujours présente.
Les **45 routes / 56 méthodes-chemins** publics rejettent les opérations non
authentifiées comme prévu ; la compatibilité OpenAPI historique est vérifiée.

Les **4 scénarios de reprise** passent : coupures réelles de Client, IAM et
PostgreSQL, puis redémarrage Commercial. Aucun résultat/compteur pendant les
pannes ; contenu, versions et session identiques après reprise. L'inventaire
Docker confirme les sept conteneurs sains, quatre Django distincts, DNS interne,
credentials propriétaires et seul port gateway publié. Les huit configurations
Compose conservées passent leur contrôle de compatibilité ; main/test restent
séparés. **Aucun échec dans les exécutions finales.** Aucun serveur de
développement local ne remplace Docker. Ce n'est pas une recette de production.

## Fichiers S13

- `backend/commercial_service/pipeline.py` : parcours borné, admission de
  lecture, cohérence, budgets et pagination ; `access.py` : timeout optionnel
  du snapshot IAM ; `tests_pipeline.py` : confiance, mémoire logique/page et
  pannes. Les chemins publics ne changent pas.
- `backend/clients/pipeline_scope.py`, `backend/iam_consumer/urls.py` : seul
  Client décide du périmètre et du nom recherché ; contrat compact privé.
  `backend/clients/tests_pipeline_scope.py` : intersection objet, révocation,
  limite/payload Unicode, signature/chemin/rejeu et refus IT.
- `infra/acceptance/pipeline_scale.py`, `pipeline_scale_verify.py` : benchmark
  et oracle/course/HTTPS ; `scripts/compose_pipeline_metrics.py` : réseau et
  RSS du vrai processus ; `compose_pipeline_recovery.py` : ajoute la coupure DB.
- `frontend/e2e/pipeline-scale.spec.ts` : 10 000 lignes, page 200, statut,
  Client 360 ; `pipeline.spec.ts` : attendre le filtre réellement appliqué
  avant le tri/page et le paramètre statut avant rechargement. Les assertions
  de comptes restent exactes ; aucun composant de production ne change.
- Ce rapport, `docs/s11-pipeline-limit-remediation.md`,
  `functional-gap-analysis.md`, `mvp-backlog.md`, `docker-compose.md` : résultats,
  historique des options et retour au backlog fonctionnel.

## Limites et retour au MVP

Le coût exact des comptes reste O(nombre d'opportunités Commercial), même si la
majorité est invisible ; seuls les échanges, la mémoire et la durée sont bornés.
Des lectures simultanées, davantage de données ou des pairs lents peuvent donc
produire un 503 de budget. Aucun débit maximal, p95 de production ou volume
supérieur n'est certifié. Le curseur serveur requiert une connexion PostgreSQL
compatible avec les transactions actuelles ; aucun pooler n'a été introduit.
La pagination est stable dans une lecture ; une modification autorisée entre
deux pages peut déplacer une ligne, comme dans le contrat public existant.
Les barrières sont globales et conservatrices ; elles peuvent temporairement
faire refuser une lecture pendant une mutation. L'acceptabilité métier des
latences et la capacité sous charge réelle restent à valider avant production.

Les quatre propriétaires, migrations, contrôles DB, audit/outbox transactionnels
et Carthago read-only restent inchangés. Aucun besoin démontré de Kafka, Redis,
nouveau service ou changement d'ownership. Le prochain candidat fonctionnel est
COM-05 : cadrage puis brouillons de campagnes manuelles, après validation AMEN
INVEST des états, du responsable et du ciblage ; aucune diffusion automatique.
