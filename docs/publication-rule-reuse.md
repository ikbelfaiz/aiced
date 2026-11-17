# Réutilisation des règles de publication

## Comportement constaté avant modification

Une règle était déjà réutilisable pour plusieurs lots. « Version » désignait un
nouvel UUID immuable côté API, et non un numéro incrémenté. Chaque proposition
créait cependant un UUID, même pour une configuration identique. L'écran et
`GET policies/` mélangeaient les 100 dernières propositions, approbations et
révocations. Une approbation ancienne pouvait donc disparaître de la liste.
La sélection manuelle filtrait seulement le type de source et le format ISO/DMY.
La règle ne portait ni version du schéma ni classification synthétique/réelle.

Le parseur vérifiait déjà XLSX, feuille unique, en-têtes et positions exacts,
limites de taille/lignes, identifiants texte et dates explicites. Les formules,
contenus actifs et liens externes étaient interdits. Les dates invalides étaient
des rejets de ligne, jamais une occasion de deviner un autre format.

Deux décisions indépendantes existaient : approbation d'une règle par un autre
utilisateur que son créateur, puis publication de **chaque lot** par un autre
utilisateur que son déposant. Ces obligations restent inchangées.

## Flux proposé et implémenté

1. Déclarer explicitement l'usage du fichier : synthétique ou opérationnel,
   son modèle versionné et son format de dates. Le nom de fichier ne sert jamais
   à classifier ou rapprocher des identités. La déclaration d'usage est une
   information fournie par l'utilisateur, pas une détection de données personnelles.
2. Valider et conserver le staging. Le serveur cherche une approbation active
   dans la **même organisation**, pour le même type, la même version du schéma,
   le même format de dates et le même usage. La colonne approuvée doit être
   renseignée et unique dans les lignes valides. Une lecture de deux règles
   maximum et des agrégats SQL suffisent ; aucun chargement global des sources.
3. Suggérer cette règle unique, sans publier. Le réviseur examine les lignes,
   confirme les exclusions éventuelles et confirme chaque publication.
4. Réutiliser le même UUID pour les prochains fichiers compatibles. Une
   proposition exactement identique (configuration et justification approuvable,
   hors espaces périphériques) renvoie la version existante, en attente ou
   approuvée ; `imports.policy_reused` conserve la trace de cette action.
5. Une modification de colonne, format, schéma, usage ou politique documentée
   nécessite une nouvelle proposition et une nouvelle approbation indépendante.
   Une justification différente est conservatrice : le système ne prétend pas
   décider si deux textes ont la même signification métier.
6. Avant d'approuver un remplacement, révoquer **explicitement** la règle active
   correspondante. Aucun remplacement, nettoyage ou consentement implicite.
   Le verrou existant par organisation et une contrainte PostgreSQL empêchent
   deux nouvelles approbations actives pour le même domaine de compatibilité.

L'écran ouvre les règles approuvées réutilisables et sépare les propositions
en attente et l'historique révoqué/non classifié. Les listes sont paginées par 100 et gardent leurs UUID,
justifications et traces. Une suggestion est recherchée directement en base,
indépendamment de la page de règles actuellement affichée.

## Historique et compatibilité

Les migrations additives `ingestion.0008` (modèle historique/tests seulement)
et `integration_store.0005` (service propriétaire en exploitation) ajoutent
`ImportPolicy.template_version`, `ImportPolicy.data_scope` et
`ImportBatch.data_scope`. Les anciennes règles ont le schéma v1 réellement
utilisé auparavant ; leur usage demeure `legacy` (non classifié). **Aucune
classification, approbation ou révocation rétroactive.** Ne pas considérer les
anciennes règles de démonstration comme une approbation AMEN INVEST.

Les nouvelles règles synthétiques/opérationnelles sont mutuellement exclusives.
L'identité d'idempotence d'un lot inclut son usage ; un rejeu ne change jamais
sa classification. Les règles/configurations, approbations acquises et
classifications des lots sont protégées par des triggers PostgreSQL. Seule
l'approbation initiale ou une révocation explicite reste autorisée. Aucun DELETE
de règle, ni modification de la version référencée par un import historique.

Les anciennes routes, structures et propriétés restent disponibles. Les champs
de création ajoutés sont optionnels pour préserver les clients existants :
absence d'usage = `legacy`, absence de version = version actuelle du catalogue.
Le workflow explicite historique reste disponible pour les anciens lots/règles
non classifiés, mais **aucune suggestion automatique** ne les requalifie comme
opérationnels. Les nouveaux dépôts de l'interface demandent un usage explicite.
Un déploiement voulant interdire aussi les clients API historiques doit planifier
cette rupture séparément ; elle n'est pas introduite silencieusement ici.

Ne pas remettre une ancienne version applicative ignorant `data_scope` en
écriture : prévoir la maintenance des imports avant tout rollback. Les
migrations ne suppriment rien et n'ont pas de retour destructif automatique.

API : mêmes routes `/api/imports/{organization_id}/upload/`, `policies/`,
`policies/{policy_id}/approve/`, `revoke/`, `batches/{batch_id}/` et `publish/`.
Ajouts : paramètre de dépôt `data_scope`, champs de règle `data_scope` et
`template_version`, champs de sortie correspondants, objet `policy_match` dans
la prévisualisation. `GET policies/?view=approved|pending|available|history&page=1` conserve une
réponse tableau ; sans paramètre, comportement historique (100 résultats/page).
Un POST identique conserve le code 201 historique mais retourne le même UUID :
ce code ne signifie donc pas qu'une nouvelle version a été créée.

## Garanties et décisions AMEN INVEST

Les droits d'import et financiers à l'échelle de l'organisation sont contrôlés
avant lecture des règles, lots ou suggestions. La publication revalide IAM,
ses fences, les droits, l'état de la règle, l'usage, le schéma et les clés dans
la transaction existante. La suggestion ne constitue jamais une autorisation.
Audit/outbox, immutabilité des snapshots, limites de ressources et séparation
des quatre services sont conservés. Aucun accès direct interschéma ajouté.

Une approbation de snapshots n'active ni identité Carthago, ni relation client/
compte, ni projection Client 360. Les décisions MAP/OWN/VIS/LIFE restent
nécessaires. Aucun fichier réel n'est utilisé dans la recette. Aucune règle
opérationnelle existante n'est automatiquement approuvée, inventée ou activée.

## Vérification Docker

Commandes depuis la racine, sans base de développement locale :

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
python scripts/compose_pipeline_diagnosis.py --test --label publication-rules-RECETTE-UNIQUE
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/publication_rules.py
python scripts/compose_import_dashboard_restart.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
```

Exécuter la preuve de persistance immédiatement après la recette navigateur :
le runner régénère des classeurs synthétiques à chaque invocation. Ne pas
utiliser `down -v` ni supprimer les historiques pour obtenir un test passant.

Résultats exécutés le 16 novembre 2026, Docker Engine 29.9.3 / Compose 5.7.0 :

| Vérification | Résultat réel |
| --- | --- |
| Build Docker React/TypeScript/Vite | Réussi |
| Régressions backend sur base de test séparée | 242 réussies : 206 générales (8 nouvelles), 5 IAM, 13 Integration, 18 Commercial |
| Suite navigateur complète, frontend compilé → Nginx → services | 44 réussies, 1 capture réservée au mode développement ignorée, 0 échec ; scénario pipeline 10 000 opportunités exécuté |
| Publication : HTTP/SQL réels | 6 groupes réussis : propositions concurrentes identiques, approbations concurrentes (1 active), réutilisation/revue, refus déposant/IT, immutabilité et audit/outbox |
| Sécurité / isolation / OpenAPI réels | 15 contrôles réussis, dont révocation IAM, credentials restreints et 4 historiques de migration |
| Contrats des routes | 52 routes / 65 méthodes-chemins ; routes retirées refusées |
| Persistance | Redémarrages réels Integration puis PostgreSQL : cellules, empreintes et provenance des 3 classeurs identiques |
| Configurations Compose | 8 configurations validées ; projets/volumes/credentials de test distincts ; aucun YAML modifié |
| Santé finale | 7 conteneurs sains dans chacun des projets application et test, 4 processus Django indépendants |
| Application principale | Migration additive Integration appliquée ; `/gestion-donnees` et 3 vues de règles autorisées HTTP 200 ; aucun dépôt/approbation pendant ce smoke test |

Les premières vérifications ont identifié un problème de la nouvelle expression
SQL : une clé JSON positionnelle texte doit être lue comme clé d'objet, pas comme
index de tableau. Corrigé et couvert par les tests. La première suite navigateur
a obtenu 42 réussites, 1 échec et 2 ignorés : le nouvel examen du corps d'une
réponse était évincé du cache inspecteur Chromium, alors que le dépôt avait
réussi. Le test vérifie maintenant le statut du POST puis relit le lot persistant,
sans retry HTTP ni suppression d'assertion. La suite complète finale a réussi.

La vérification OpenAPI à travers le gateway a également révélé des noms
d'enum différents de ceux du générateur mono-processus. Le vérificateur suit
uniquement les références des trois nouveaux champs `data_scope` et impose
exactement `legacy/synthetic/operational`. Aucun champ du contrat préexistant
n'est supprimé du contrôle, et la baseline historique n'est pas modifiée.

Preuves locales exclues du Git :
`.local/compose-test/s161-publication-rules-final/`,
`regression-report.json`, `publication-rules-report.json`,
`import-dashboard-sql.json`, `import-dashboard-restart.json`,
`integration-report.json`, `routes-report.json` et `container-inventory.json`
sous `.local/compose-test/`. La première tentative navigateur est conservée
dans `publication-rules-first-browser.{json,log}`. L'application principale est
accessible à `http://127.0.0.1:5187/gestion-donnees` ; sa base existante a été
conservée et aucun import synthétique de recette n'y a été ajouté.

Le défaut intermittent HTTP 503 du pipeline S16.1 reste **ouvert**, même si une
recette ultérieure passe ; aucune modification spéculative de ce pipeline.
Ces résultats locaux ne constituent pas une qualification de production.

## Fichiers concernés

- `backend/ingestion/{models,services,views,matching,tests}.py`, migration 0008 ;
  `backend/integration_store/models.py`, migration 0005 : version, classification,
  dédoublonnage, appariement borné et contraintes d'historique.
- `backend/contracts/additions.py` : seules les propriétés de schéma additives
  nommées sont admises ; le contrat historique n'est pas réécrit.
- `frontend/src/features/imports/DataManagement.tsx`,
  `frontend/src/lib/workspace-api.ts` : vues de règles, déclaration d'usage,
  suggestion et revue inchangée.
- `frontend/e2e/{import-dashboard,workspace}.spec.ts` : réutilisation réelle,
  séparation des usages, proposition/approbation et publication par réviseur.
- `infra/acceptance/{bootstrap,publication_rules_migrate,publication_rules}.py` :
  migration explicite sous le propriétaire existant et preuves HTTP/SQL.
- Ce document, analyse des écarts, backlog et questions ouvertes. Aucun fichier
  Compose, service, port, réseau, credential ou volume modifié.
