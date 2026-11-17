# S16.1 — diagnostic du pipeline : régression ouverte

Acceptation utilisateur lors du lancement S17 : **incrément de diagnostic et
d'observabilité terminé et accepté**, défaut intermittent 503 non résolu,
conservé comme risque de release ouvert. Les travaux fonctionnels S17 sont
autorisés sans changement spéculatif du pipeline. Les formulations historiques
ci-dessous décrivent la validation technique antérieure à cette acceptation ;
elles ne signifient pas qu'un correctif a été livré.

## Décision de validation

Le 16 novembre 2026, trois suites navigateur complètes dans Docker passent,
mais **le 503 historique n'est pas reproduit et sa cause reste indéterminée**.
Il n'existe donc pas de correction causale démontrée, ni de comparaison
avant/après correction. L'incrément de diagnostic S16.1 est accepté comme
terminé ; le défaut intermittent et la validation de release S16 restent ouverts.
Les succès ci-dessous ne remplacent pas le diagnostic demandé.

Le budget de quatre secondes, les lots de 500, les plafonds HTTP/SQL,
l'autorisation Client, les relectures IAM et les barrières restent inchangés.
Aucune migration, modification de contrat public, nouvelle infrastructure ou
activation source réelle. Aucun retry automatique de 503 ajouté.

## Séquence connue de l'échec historique

Dans les deux rapports S16 conservés : suite complète avec le scénario de
10 000 dossiers immédiatement avant `Pipeline persists existing creation/status
workflow and rejects a concurrent stale edit`. Ce dernier crée un dossier et
une opportunité, change son statut, vérifie un PATCH obsolète, crée huit autres
opportunités, revient au pipeline et recherche le nom synthétique du dossier.
L'assertion attend neuf résultats ; l'ancien résultat en cache vaut un puis
disparaît avec une réponse 503.

Requête connue : `GET /api/opportunities/?search=SYNTHETIQUE+PIPELINE+<horodatage>`.
Le précédent journal Commercial indiquait 503 et 86 octets. Son corps, ses
identifiants de corrélation et les traces synchronisées des pairs n'avaient pas
été enregistrés. Ils ne peuvent pas être reconstruits à partir du rapport
Playwright. La condition supplémentaire qui déclenchait cet échec demeure
inconnue : ne pas l'attribuer au budget, à Nginx ou à IAM sans preuve.

## Instrumentation livrée

- `core/request_metrics.py`, `core/middleware.py`, `core/logging.py` : ID local
  généré par requête, durée, code HTTP, nombre et durée des exécutions SQL pour
  le pipeline et les routes internes. ContextVar libérée même sur exception.
  Les identifiants entrants ne sont pas acceptés comme autorité de corrélation.
- `internal_api/client.py` : chemin interne statique, pair, durée/plafond,
  expiration, statut et ID de réponse du pair. Ce lien permet de suivre
  Gateway → Commercial → Client → IAM sans modifier la signature ni sa portée.
- `commercial_service/pipeline.py` : nombre de lots, budget restant, épuisement
  du budget, refus de barrière IAM/Client et erreur base distincts dans les logs.
  Le comportement de refus reste identique.
- Nginx : ID de réponse amont, temps total et temps amont ; aucun URL,
  query string, cookie, secret ou payload ajouté aux journaux Gateway.
- `frontend/e2e/pipeline-diagnostics.ts`, deux specs pipeline : observation des
  vrais départs, annulations et réponses, ID, timings, compteurs ou corps
  d'erreur. Aucune modification des assertions, attentes ou retries. Ces
  captures concernent exclusivement les fixtures synthétiques de recette.
- `scripts/compose_browser.py` sépare les captures de chaque invocation.
  `compose_pipeline_diagnosis.py` archive navigateur, logs des cinq conteneurs
  concernés, statistiques Docker et état des conteneurs. Les premières captures
  de requêtes étaient cumulatives ; utiliser les horodatages de `run.json` pour
  ces archives. Les logs serveurs et rapports Playwright sont propres à chaque run.
- `pipeline_evidence_summary.py` lie les spans et résume les ressources.
  `compose_pipeline_concurrency.py` compare six lectures simultanées réelles
  en vagues de deux puis quatre à l'oracle séquentiel, sans retry.
  `compose_pipeline_recovery.py` conserve aussi corps/ID/durée des erreurs
  pendant les arrêts réels. Les captures restent dans `.local/compose-test/`.

Le formatter n'émet que les champs de métriques autorisés, jamais les messages
arbitraires, SQL, credentials ou payloads. Trois nouveaux tests vérifient cette
limitation et la portée de l'ID. SQL mesure les appels Django `execute`, pas les
FETCH implicites du curseur ni un profil PostgreSQL complet.

## Mesures observées, sans correction comportementale

Docker Engine **29.9.3**, Compose **v5.7.0**, projet `aiced-test`, Nginx
`http://127.0.0.1:5188`, base jetable existante, données synthétiques uniquement.
Les tests ont été lancés séquentiellement : aucune panne ou mutation de fixture
d'autorisation n'a été orchestrée pendant les suites navigateur.

| Exécution complète | Résultat | Médiane / maximum du pipeline serveur |
|---|---|---|
| `s161-baseline-full` | 39 passés, 1 skip développement, 0 échec | 1,668 / 2,090 s |
| `s161-baseline-full-2` | 39 passés, 1 skip développement, 0 échec | 1,646 / 2,017 s |
| `s161-final-full-3` | 39 passés, 1 skip développement, 0 échec | 1,661 / 2,046 s |
| `s161-isolated` — deux tests pipeline | 2 passés | 1,549 / 1,686 s |

Le scénario précis dure respectivement environ 14,7 / 15,3 / 15,4 s en suite
complète, contre 15,0 s isolé. Chaque suite complète contient 29 lectures serveur
pipeline réussies et un refus IT 403 attendu ; aucun 503 pipeline dans ces runs.
Les requêtes annulées par Chromium continuent parfois jusqu'au terme côté
WSGI : chevauchement réel confirmé, **causalité avec l'ancien 503 non prouvée**.
Le scénario précédent à 10 000 lignes passe lui aussi dans chaque suite.

Une lecture sur ce fond de données parcourt 21 lots, avec 26 RPC Commercial
(24 Client + 2 IAM), auxquels s'ajoutent 24 RPC Client → IAM : **50 HTTP internes**.
Un exemple corrélé (`a2c0bd62-33ca-4b50-b112-cfad5f02490c`) prend 1,660 s :
1,498 s d'appels sortants Commercial, 31 SQL Commercial / 17,4 ms cumulés,
71 SQL Client / 170,4 ms, 182 SQL IAM / 216,1 ms. Le scan termine avec
2,520 s de budget restant.
Ce sont des exemples et médianes de recette, pas un p95 ni un engagement de charge.

Vagues simultanées, 10 000 résultats autorisés par lecture : deux utilisateurs
1,834–1,835 s ; quatre utilisateurs 2,522–2,688 s ; six réponses 200 exactement
identiques à l'oracle, sans différence de compte, page ou statut.

Pics Docker sur les trois suites : Commercial 72,86 MiB / 46,26 % CPU,
Client 101,60 MiB / 105,67 %, IAM 73,89 MiB / 91,06 %, PostgreSQL 78,69 MiB /
123,74 %. Le pourcentage Docker peut dépasser 100 sur plusieurs cœurs.
Ces échantillons ne démontrent pas l'état de la machine lors des échecs
historiques et ne prouvent pas une absence de contention à toute charge.

## Vérifications complémentaires

Toutes les vérifications ci-dessous ont été réellement exécutées dans le
projet Docker isolé, après les suites navigateur, sans chevauchement :

| Vérification | Résultat |
|---|---|
| Régression backend | **228 passés** : socle/Client/contrats 192, IAM 5, Integration 13, Commercial 18 |
| `pipeline_scale_verify.py` | **12 groupes passés**, oracle 10 000, pages profondes, égalités/NULL, nom seul, droits retirés/expirés, courses barrières IAM/Client, PATCH concurrent, stale 409, audit/outbox, timeout, signatures/rejeu |
| `pipeline.py` | **5 groupes passés**, périmètres, filtres, PATCH simultanés, audit/outbox, révocation réelle et session expirée |
| `compose_pipeline_concurrency.py` | **6 lectures passées**, vagues de 2 et 4, identiques à l'oracle 10 000 |
| `compose_pipeline_metrics.py` | **200 / 10 000 / 1,854 s**, 50 HTTP internes ; processus Commercial 76 996–77 024 KiB RSS échantillonné |
| `compose_pipeline_recovery.py` | **4 groupes passés** : trois dépendances réellement arrêtées puis récupérées, redémarrage Commercial, mêmes versions/comptes/réponse après retour |
| `source_mapping.py` | **6 groupes passés**, six cas synthétiques, refus hors périmètre/import-only revocation, anti-rejeu, aucune identité/relation persistée, snapshot non modifiable |
| `compose_source_mapping_recovery.py` | **6 groupes passés**, pannes Integration/Client/IAM, redémarrages Integration/Client/DB, six fixtures/provenances inchangées |
| `verify.py` | **15 groupes passés**, rôles SQL isolés, quatre historiques de migrations, OpenAPI, CSRF, révocation, rollback et livraison audit/outbox idempotente |
| `routes.py` | **51 routes / 64 méthodes-chemins** vérifiés |
| Inventaire et Compose | **7 conteneurs sains**, quatre processus Django distincts, DNS interne, port Gateway seul ; **8 configurations validées**, secrets/volumes test distincts |

Les écrivains exclusifs des courses grand volume attendent 1,478 s (IAM) et
1,627 s (Client), sous le plafond existant de cinq secondes. Les contrôles
vérifient le refus sans page ni statistique partielle après révocation/expiration,
pendant une mutation exclusive, un timeout ou une signature invalide.

Les 503 **provoqués volontairement par les arrêts** sont corrélés dans
`pipeline-recovery-report.json` et `s161-recovery-{gateway,commercial,client,iam,db}.log` :

| Dépendance arrêtée | ID Commercial / Gateway | Temps HTTP | Résultat |
|---|---|---:|---|
| Client | `d6a0f251-2859-4828-a25e-9bb8c56252e5` | 4,033 s | 503, aucune donnée |
| IAM | `c8fbace1-dc8c-4aef-8706-d7baa16d841d` | 3,994 s | 503, aucune donnée |
| PostgreSQL | `4e4324dd-ef5c-4a3f-95ca-ed4c7f1e377d` | 3,006 s | 503, aucune donnée |

Corps commun : `error.status=503`,
`error.details.detail="Service d’autorisation indisponible."`.
Les traces montrent un échec de connexion au pair, puis le 503 Commercial
relayé par Gateway ; ce ne sont pas les échecs historiques du navigateur.
En panne réseau, un appel configuré à trois secondes a pris environ 3,97 s :
le timer existant ne peut pas interrompre une résolution/connexion avant que
la socket soit disponible. Le budget pipeline est vérifié entre opérations,
**pas une garantie d'interruption murale exacte**, et l'authentification DRF
initiale le précède. Cette limite observée est consignée, sans l'attribuer
abusivement au 503 historique ni modifier les délais sans diagnostic causal.

## Fichiers de cet incrément

Backend : `backend/core/request_metrics.py`, `backend/core/tests_request_metrics.py`,
`backend/core/logging.py`, `backend/core/middleware.py`,
`backend/internal_api/client.py`, `backend/commercial_service/pipeline.py`.
Gateway : `infra/gateway/nginx.conf.template` (journal seulement).
Navigateur : `frontend/e2e/pipeline-diagnostics.ts`,
`frontend/e2e/pipeline.spec.ts`, `frontend/e2e/pipeline-scale.spec.ts`.
Scripts : `scripts/compose_browser.py`, `scripts/compose_pipeline_diagnosis.py`,
`scripts/pipeline_evidence_summary.py`, `scripts/compose_pipeline_concurrency.py`,
`scripts/compose_pipeline_recovery.py`.
Documentation : ce rapport, `docs/mvp-backlog.md`, `docs/functional-gap-analysis.md`.
Les autres modifications préexistantes du workspace ne relèvent pas de S16.1.

## Reproduire et conserver la prochaine occurrence

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d
docker compose -f compose.yaml -f compose.test.yaml restart gateway
python scripts/compose_pipeline_diagnosis.py --test --label nouvelle-suite-complete
python scripts/pipeline_evidence_summary.py .local/compose-test/s161-nouvelle-suite-complete
python scripts/compose_pipeline_diagnosis.py --test --label pipeline-seul pipeline.spec.ts
python scripts/compose_pipeline_concurrency.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/pipeline_scale_verify.py
python scripts/compose_pipeline_recovery.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
```

Chaque label d'archive doit être neuf. Ne pas démarrer simultanément les pannes,
révocations, benchmarks mutables et suites navigateur. Conserver l'environnement
en cas de nouvel échec avant toute recréation de conteneur, puis relier le
`X-Request-ID` navigateur à Nginx et aux `peer_request_id` Client/IAM. Comparer
dernière phase, budget, temps RPC/SQL, barrières et ressources au même instant.

## Limites et prochaine étape

Le parcours reste O(nombre global d'opportunités), même avec une recherche
étroite ; une annulation navigateur n'annule pas automatiquement le travail
WSGI. Les contrôles de sécurité continuent à refuser sans résultats partiels
au-delà du budget ou pendant une indisponibilité. Plus de quatre lectures
simultanées et plus de 10 000 dossiers de référence ne sont pas qualifiés ici.
La volumétrie des nouveaux logs de diagnostic doit être surveillée.

La prochaine étape technique reste **capturer et expliquer le 503 historique**
avec ces diagnostics, puis appliquer une correction justifiée et refaire trois
suites complètes après cette correction. Les trois succès présents ne sont pas
trois validations post-correctif. Ne pas fermer l'incident 503 sur cette seule base.
Le rapprochement réel, les projections Client 360 et les décisions AMEN INVEST
MAP/OWN/VIS/LIFE restent bloqués ; l'aperçu S16 reste synthétique et en lecture seule.
