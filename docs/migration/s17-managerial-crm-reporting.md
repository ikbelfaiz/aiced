# S17 — Pilotage CRM sur données autorisées

## Périmètre et autorisations

Page `/pilotage-crm`, navigation **Pilotage CRM**, sous les habilitations CRM
existantes. Il ne s'agit pas d'un nouveau privilège direction. L'absence de
matrice direction/équipe approuvée interdit toujours de voir les dossiers,
agendas ou brouillons d'autrui hors des règles existantes. Aucun rôle, droit,
schéma propriétaire, fichier Compose, credential ou modèle de base ajouté.

Le serveur Client & CRM calcule `GET /api/clients/managerial-report/` ; filtres
optionnels `date_from`, `date_to`, `kind=call|email|meeting|visit`. Réponse
additive au dictionnaire descriptif S16, avec `portfolio.quality` et
`portfolio.by_kind`. Les autres sources restent `GET /api/opportunities/?page_size=1`
et `GET /api/campaigns/?page_size=1`, dans Commercial. Aucun accès direct aux
schémas IAM/Commercial/Integration depuis le calcul Client.

`clients.view` est obligatoire pour la nouvelle API et la page. Le queryset
Client existant détermine les objets affectés ou de l'organisation explicitement
accordée, sans hiérarchie d'équipes inventée. Le nom de la page et la capacité
`reports.view_global` ne donnent aucun droit objet supplémentaire. Un utilisateur
ayant seulement `clients.view` voit son portefeuille ; les autres métriques
sans habilitation sont `null` / « habilitation requise », jamais des zéros.
Pour S17, les capacités doivent concerner au moins une même organisation avant
d'activer un indicateur d'activité ; les querysets existants appliquent ensuite
l'intersection objet complète. Des droits clients en A et activités en B ne
privent pas du portefeuille autorisé en A et n'autorisent aucun agrégat en B.
IT et superuser n'ont aucun accès implicite. Aucun droit financier n'est requis
ou déduit pour ces comptes opérationnels.

## Dictionnaire des indicateurs

| Indicateur | Source et calcul exact | Base temporelle | Périmètre d'autorisation / limites |
|---|---|---|---|
| Clients accessibles | `Party`, nombre de lignes, `prospect IS NULL` | Stock courant, indépendant de la période | `client_queryset(actor, clients.view)` avant compte ; aucun client dérivé d'un snapshot Excel |
| Clients physiques / moraux | Même queryset, `COUNT` par `Party.kind` existant | Stock courant | Même portée ; deux types existants seulement, aucun segment financier |
| Profils techniquement complets / incomplets | Réutilisation S15 `quality.summary` et `annotate_quality` : présence des champs configurés, poids égaux, `floor(100 * présents / nombre de champs)` ; complet si 100, incomplet sinon | Valeurs CRM actuelles, aucun historique déduit | Même clientèle visible hors prospects ; défaut email/téléphone/profession/secteur, `AICED_PROFILE_COMPLETENESS_FIELDS` adaptable ; définition vide = indisponible, pas zéro ; définition technique provisoire, ni KYC ni validité métier |
| Champs CRM absents | Pour chaque champ configuré, nombre de profils du même queryset où valeur NULL, absente ou entièrement blanche | Stock courant | Absences par champ non exclusives ; leur somme n'est pas un nombre de clients ; aucun rapprochement ou correction automatique |
| Interactions, répartition par type et série quotidienne | `Interaction`, `COUNT` groupé par type et jour de `occurred_at` | `date_from` inclus → lendemain de `date_to` exclu, dans le fuseau du rapport ; filtre `kind` facultatif | Politique S16 `interaction_history` : intersection `clients.view` et `interactions.view`, y compris visibilité prospect ; compte d'enregistrements actuellement présents, sans preuve de contact ni résultat déduit |
| Mes rendez-vous, types et série quotidienne | `Appointment`, `COUNT` par type et jour de `starts_at` | Début dans la même période ; même filtre `kind` | Politique agenda S12, propriétaire = utilisateur courant, organisations autorisées clients/interactions ; rendez-vous non assimilé à une interaction réalisée ; aucun agenda collectif |
| Relances prospects | `Prospect.next_action_date` : `< business_date`, `=`, `>`, NULL | Stock à la date métier du calcul, indépendant de période/type | Queryset prospects autorisé existant ; tous statuts, y compris clos comme dans S9/S16 ; une date n'implique pas une action effectuée |
| Opportunités / statuts | `count` et `statuses` du pipeline public existant, ouvert/gagné/perdu | Statut courant, toutes dates | Commercial demande chaque décision objet à Client, y compris pour les prospects autorisés ; autorisation avant comptes/pages ; aucun montant, revenu, conversion ou score calculé |
| Mes brouillons de campagnes | `count` de l'API campagnes S14 existante | Stock courant, toutes dates | `opportunities.view`, organisations IAM autorisées et créateur courant ; aucune cible, activation, communication ou activité historique déduite |

Le rapport Client réutilise le fuseau `AICED_REPORT_TIME_ZONE`, **Africa/Tunis**
par défaut, y compris les bornes à minuit ; le fuseau du navigateur n'en change
pas les calculs. Période par défaut : 30 jours inclusifs jusqu'à la date métier.
Maximum 93 jours, années 1900 à 9998, début ≤ fin. Les jours vides sont des
zéros d'enregistrements dans la portée autorisée, pas un historique inventé.
Les graphiques distinguent les stocks courants et les activités de période.
Les décisions formelles de fuseau et de définitions restent à confirmer.

## Interface et intégrité

Cartes clientèle/complétude, graphiques de types de clients, champs manquants,
relances et statuts d'opportunités ; courbe quotidienne interactions/rendez-vous.
Chaque graphique possède une table de valeurs accessible. Liens vers clients,
interactions, agenda, relances, opportunités et brouillons existants. Le filtre
de période/type conserve l'URL ; rechargement et affichage mobile sont couverts.
L'écran réutilise `CommercialActivity`, avec un mode de pilotage explicite,
et les composants/design existants, sans modifier les workflows métier.

Chaque source affiche son erreur et masque ses anciennes cartes et courbes.
Les sources de propriétaires indépendants restent distinguées ; aucun snapshot
global simultané interservices n'est revendiqué. La clef de cache S17 inclut
la session et les affectations IAM connues ; un changement de grants connu
déclenche de nouvelles lectures. La vérification serveur reste obligatoire à
chaque requête. La page n'est pas un flux temps réel de révocations ou mutations.

La nouvelle vue réutilise les barrières partagées IAM/Client sans attente,
READ COMMITTED après admission, les relectures IAM avant/après calcul, le
budget de traitement de quatre secondes et `work_mem=4MB` de S16. Les erreurs
SQL, changements de grants ou incohérences de comptes échouent sans résultat
partiel. Les agrégats sont SQL, sans liste globale d'identifiants côté navigateur
ou parcours HTTP non borné. Les quatre champs et les 93 points par série bornent
la sortie ; les agrégats nécessitent néanmoins de lire les lignes éligibles.

Lecture seule : aucune écriture CRM/source, journal métier ou outbox nouvelle
pour ces calculs. Les sessions, projections IAM et nonces signés suivent leur
comportement existant ; l'absence de nouvel événement métier n'implique pas
l'absence de logs d'authentification. Les écritures effectuées depuis les liens
existants conservent leur audit/outbox transactionnels.

## Validation Docker

Validation exécutée le 16 novembre 2026, Docker Engine 29.9.3 / Compose v5.7.0.
Environnement :
projet isolé `aiced-test`, Nginx `http://127.0.0.1:5188`, base jetable et fixtures
synthétiques seulement. Aucun import de référence réelle ni processus backend
local. Le compte `synthetic.s17.empty`, préparé seulement dans cette base par
`infra/acceptance/managerial.py`, possède des droits de lecture affectés et
aucun dossier, rendez-vous ou brouillon. Son secret provient du fichier privé
de recette et n'est ni inscrit ici ni committé.

| Vérification réellement exécutée | Résultat |
|---|---|
| Build TypeScript/Vite et images Docker | Réussis ; avertissement de taille de bundle existant, sans échec |
| Régression backend complète | **234 tests passés** : 198 socle/Client/contrats, 5 IAM, 13 Integration, 18 Commercial ; dont 6 nouveaux tests S17 |
| Navigateur S17 ciblé | **5 tests passés** : vrais comptes et agrégats, création d'interaction, graphiques/tables, période/type/Tunis, viewport 390 px, erreurs/droits, vide réel, quatre pannes Docker et récupération |
| Navigateur complet final, scale activé | **44 passés, 1 skip développement, 0 échec**, 45 scénarios, environ 4 min ; 10 000 opportunités, scénario neuf opportunités et droits d'organisations disjointes inclus ; première exécution complète également 44/1/0 |
| `managerial.py` | **7 groupes passés** : parité listes/qualité/activité autorisées, vide réel/IT/anonyme, organisations disjointes, invariants lecture seule, barrières IAM/Client, révocation IAM et récupération même session, validation |
| `verify.py` | **15 groupes passés** : SQL isolé, quatre historiques, OpenAPI, CSRF, révocation, audit/outbox atomiques et déduplication |
| `routes.py` | **52 routes / 65 méthodes-chemins** ; ajout GET compatible seulement |
| Inventaires Docker test et application locale | **7 conteneurs sains chacun**, quatre processus Django indépendants, DNS interne, port Gateway seul exposé |
| Validation Compose | **8 configurations** validées ; aucun fichier Compose modifié, volumes et secrets test distincts |

Les six lectures mesurées de la recette HTTP finale prennent environ
**0,121–0,146 s** pour le rapport Client dans ces fixtures. Il s'agit de mesures
ponctuelles, sans garantie p95 ni test de charge général. Les opportunités gardent
leur coût global et budget S13 ; aucune optimisation ou nouvelle limite pipeline
n'a été introduite par S17.

Le test navigateur de pannes arrête réellement Client, Commercial, IAM et
PostgreSQL, source par source. Il constate la disparition des KPI/courbes
concernés ; les panneaux du propriétaire indépendant restent disponibles
lorsque c'est autorisé. Après chaque remise en service, il recharge la page et
compare toute la réponse Client à l'état initial, hors `generated_at` :
portefeuille, complétude, activités, dates et relances identiques. Les arrêts et
redémarrages changent les processus, sans perte des données CRM persistées.

Les premières exécutions de développement ont signalé une assertion backend
envoyant du multipart au lieu du JSON prévu et une requête navigateur lancée
avant la fin de la connexion. Le test de méthode utilise maintenant JSON et
le helper attend la navigation authentifiée ; les suites complètes finales ont
ensuite été exécutées avec les résultats ci-dessus. Aucun échec métier n'a été
masqué par un retry ou classé attendu.

Preuves exclues : `.local/compose-test/s17-targeted-browser.json/.log`,
`s161-s17-full/` et `s161-s17-final/` (rapports complets, logs corrélés, ressources
et états Docker ; seconde exécution après vérification des droits disjoints),
`managerial-report.json`, `regression-report.json`, journaux de tests,
`s17-contract-security.log`, `routes-report.json`. Capture mobile inspectée :
`.local/ui-review/screens/managerial-mobile.png`. Les 503 provoqués par les
scénarios de panne sont attendus et distincts de l'incident intermittent S16.1 ;
le scénario pipeline historiquement défaillant passe dans cette suite, sans
que cela démontre la résolution du défaut.

La stack locale a été rafraîchie après validation avec les mêmes sources :
`docker compose up --build -d`, puis mise à jour finale de l'image backend
vérifiée avec `docker compose up -d --no-build` et `docker compose restart gateway`.
Adresse : **http://127.0.0.1:5187/pilotage-crm**. Smoke en lecture seule : nouvelle
API et route SPA HTTP 200 ; aucun scénario de création, révocation, fixture ou
panne n'a été exécuté contre la base de l'application locale. Les scénarios
fonctionnels complets et les comptes supplémentaires S17 restent dans la base
de test isolée. Ceci n'est pas un déploiement ni une validation de production.

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/managerial.py
python scripts/compose_browser.py --test managerial.spec.ts
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
python scripts/compose_pipeline_diagnosis.py --test --label s17-full
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_inventory.py --test
```

Ne pas lancer les scénarios de pannes/révocations simultanément à d'autres
suites. Le test navigateur de pannes réelles ne s'active qu'avec le marqueur
`AICED_E2E_ISOLATED=1`, fourni par le runner `--test` ; il arrête uniquement les
services du projet explicitement `compose.yaml + compose.test.yaml`, les remet
en route dans `finally` et attend la disponibilité avant le scénario suivant.
Les attentes de remise en service ne sont pas des retries de 503 métier.
Choisir un label d'archive neuf à chaque exécution du runner de diagnostic ;
les dossiers `s17-full` et `s17-final` ci-dessus sont conservés comme preuves.

## Fichiers et contrats

- Backend : `clients/managerial_reporting.py`, `clients/reporting.py`
  (point d'extension de calcul, comportement S16 conservé),
  `clients/tests_managerial_reporting.py`, `config/urls.py`, `contracts/additions.py`.
- Frontend : `features/reporting/ManagerialPortfolio.tsx`,
  `features/reporting/CommercialActivity.tsx`, `app/App.tsx`,
  `components/layout/AppShell.tsx`, `e2e/managerial.spec.ts`.
- Recette : `infra/acceptance/managerial.py`, `scripts/compose_browser.py`
  (marqueur d'isolation seulement). Documentation : ce rapport, analyse des écarts,
  backlog, questions ouvertes et statut d'acceptation S16.1.
- Une route GET additive, aucun changement des routes/champs historiques,
  aucune migration de base ou nouvelle capacité IAM.

## Décisions AMEN INVEST et risques de release

À approuver : matrice direction/équipe et éventuelle attribution des activités,
visibilité des agendas/brouillons d'autres créateurs, définition de contact
effectif/résultat, taxonomie/validité des profils, fuseau définitif, historique
et export managériaux éventuels. Aucun de ces éléments n'est inféré par S17.
Les formules et sources des KPI financiers, valorisations et rétention restent
exclues. Les décisions source MAP/OWN/VIS/LIFE restent requises avant tout
rapprochement client/compte Carthago : aucune activation dans cet incrément.

**Incident S16.1 : intermittent HTTP 503 pipeline toujours ouvert.**
L'incrément de diagnostic/observabilité est accepté ; la correction du défaut
ne l'est pas et aucune correction n'est revendiquée. Le panneau opportunités
S17 consomme la même API : il peut être indisponible et masque alors ses données.
L'instrumentation, les plafonds et le refus fermé sont conservés sans changement
spéculatif. Voir [l'incident](../s16-1-pipeline-regression.md). Un succès de
recette locale n'établit ni sa résolution ni une préparation à la production.

Prochain incrément recommandé : obtenir la matrice managériale et les décisions
d'attribution ; implémenter ensuite uniquement les vues collectives approuvées.
Le risque 503 reste suivi séparément avec les diagnostics disponibles.
