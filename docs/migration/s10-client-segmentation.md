# S10 — PAN-01, profession et secteur CRM

## Fonction livrée

Le Panorama existant `/clients` conserve sa navigation et ses fiches 360.
Deux listes profession/secteur proposent les valeurs déclarées dans
`CRMProfile`, leurs effectifs autorisés, « Non renseigné » et « Renseigné ».
Elles se combinent avec recherche nom/identifiant, type de personne,
tri et pagination. Les changements de filtre réinitialisent la page ;
l'URL conserve la sélection au rechargement. Les aperçus de maquette restent
distincts et n'utilisent pas les données de ces filtres.

Les effectifs des options portent sur **tous les clients visibles avant les
filtres**, pas seulement la page ou la sélection courante. Le compteur existant
du Panorama porte sur le résultat filtré. Les prospects sont exclus des deux.
Les erreurs de liste ou d'options masquent les lignes, options précédentes et
effectifs en cache ; la reprise recharge les deux ressources.

## API et compatibilité

`GET /api/clients/` conserve sa réponse et son ordre par défaut UUID. Ajouts
optionnels, sans modifier recherche/type/pagination existants :

| Paramètre | Sens |
|---|---|
| `profession`, `sector` | Libellé CRM exact, sensible à la casse et aux espaces, maximum 120 caractères ; omettre si aucune sélection |
| `profession_missing`, `sector_missing` | `true` = absent/vide/uniquement espaces reconnus par PostgreSQL ; `false` = renseigné |
| `ordering` | `id` (défaut), `display_name`, `-display_name`, `profession`, `-profession`, `sector`, `-sector` |

Une valeur exacte et un filtre de présence sur le même champ sont incompatibles
(400), comme un filtre invalide. Les tris CRM placent les absences en dernier
dans les deux sens ; UUID départage toutes les égalités. Aucun ordre métier
de profession/secteur n'est déduit.

Nouvelle lecture Client & CRM : `GET /api/clients/filter-options/` :

```json
{
  "profession": {"values": [{"value": "SYNTHETIQUE Exemple", "count": 2}], "missing_count": 1},
  "sector": {"values": [], "missing_count": 3}
}
```

Les variantes de casse, accents ou espacement ne sont pas fusionnées. Les
libellés sont présentés entre guillemets avec échappement des espaces de
contrôle pour rendre ces différences explicites. Un profil CRM absent équivaut
à une valeur manquante ; aucune écriture, correction ou taxonomie n'est créée.
Les noms de paramètres frontend sont `profession`, `sector`, leurs suffixes
`_missing`, `ordering`, avec les paramètres historiques `recherche`, `type`,
`page`, `taille` conservés.

Les 38 routes historiques et leurs réponses restent compatibles. Le contrôle
OpenAPI autorise explicitement ces cinq paramètres optionnels sur la seule
liste Clients et les ajouts de lecture S8–S10 : total 41 routes, 50 couples
méthode/route. La baseline historique n'a pas été régénérée.

## Sécurité et données

`clients.view` et `client_queryset` s'appliquent avant tout filtre, regroupement,
effectif, option et pagination. Les scopes assigné/organisation restent ceux
de l'IAM, sans privilège financier implicite pour IT. Aucun ID, libellé ou
effectif d'objet non visible ne participe aux résultats.

Pas de migration, nouveau champ, service, propriétaire SQL ou configuration
Compose. Qualification/édition CRM, audit/outbox et coordination de révocation
restent dans les services existants. Carthago reste strictement en lecture seule.
Les données créées par les tests sont synthétiques et identifiées comme telles.

## Validation Docker du 15 novembre 2026

Docker Engine 29.9.3 et Compose v5.7.0 réellement disponibles. Reconstruction
TypeScript/Vite et backend réussie dans `aiced-test`, accès navigateur par
Nginx sur `http://127.0.0.1:5188/clients`, sans serveur local de substitution.

| Suite exécutée | Résultat |
|---|---|
| Régression générale backend | 157 tests réussis, dont 6 S10 |
| IAM / Integration / Commercial propres | 5 / 8 / 5 réussis ; total backend 175 |
| Chromium compilé, toutes les suites existantes et S10 | 19 réussis, 1 ignoré (maquettes réservées au mode développement), aucun échec final |
| Deux nouveaux workflows navigateur | Saisie réelle Client 360 → filtres combinés/tri/pages/rechargement/mobile → fiche ; refus IT et masquage des options/lignes après erreur puis reprise |
| Sondes S10 réelles IAM/Nginx | 3 réussies : options/effectifs assignés, valeurs forgées invisibles, révocation immédiate liste/options |
| Sondes quatre services existantes | 15 réussies : isolation SQL, contrats, signatures/rejeu, concurrence/révocation, rollback et livraison audit/outbox |
| Routes publiques | 41 routes / 50 couples méthode-route ; anonyme et routes retirées refusés |
| Migrations | `makemigrations --check --dry-run` : aucun changement ; `migrate --check` réussi |
| Compose | 8 configurations équivalentes et isolation projet/volume/credentials test confirmées |
| Inventaire final | 7 conteneurs sains, 4 processus Django distincts, DNS interne et credentials propres ; gateway seul port publié |
| Vérification des fichiers | `git diff --check` réussi |

Les tests d'isolation ont d'abord été exécutés avant l'implémentation : échecs
attendus, filtres absents et endpoint 404. Ils ont ensuite révélé le comportement
DRF des booléens d'un QueryDict assimilés à des cases HTML : les filtres absents
devenaient `false`. La validation utilise désormais un dictionnaire conservant
l'absence des clés. Tous les tests finaux passent. Le dernier test de tri ajouté
a été inclus dans une relance complète backend en conteneur avec les sources
montées en lecture seule ; le code applicatif servi n'a pas changé entre les
deux passages. La capture mobile a été inspectée visuellement.

Les nouveaux tests backend couvrent combinaison/type/recherche/pages, variantes
exactes, profil absent, vide/espaces, tri stable et absences en dernier, scopes
assignés/inter-organisations, exclusion prospects, IT/anonyme et révocation.

Commandes de validation (sondes de révocation séparées du navigateur) :

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
python scripts/compose_browser.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/segmentation.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_validate.py
python scripts/compose_inventory.py --test
```

## Fichiers S10

- Backend : `backend/clients/segmentation.py`, `backend/clients/tests_segmentation.py`,
  `backend/clients/views.py`, `backend/config/urls.py`, `backend/contracts/additions.py`.
- Frontend : `frontend/src/features/clients/ClientsPage.tsx`,
  `frontend/src/features/clients/SegmentationFilters.tsx`, `frontend/src/lib/api.ts`,
  `frontend/e2e/segmentation.spec.ts`.
- Validation : `infra/acceptance/segmentation.py`, `infra/acceptance/verify.py`
  (libellé de résultat actualisé).
- Documentation : ce rapport, `docs/functional-gap-analysis.md`,
  `docs/mvp-backlog.md`, `docs/open-questions.md`.

Les changements S7–S9 déjà présents dans l'espace de travail sont conservés.

## Limites et prochaine étape

Pas de nomenclature approuvée, fusion de variantes, graphique, scoring,
classification d'investissement ni KPI financier. Les décisions de nomenclature
restent à AMEN INVEST (`open-questions.md`). Les listes de valeurs ne sont pas
des référentiels ; pour des volumes importants de libellés distincts, mesurer
les performances avant d'envisager une recherche paginée d'options ou des index.

Prochain incrément recommandé : COM-03, pipeline des statuts d'opportunités
existants, avec périmètre autorisé avant agrégats/pages et autorisation Client
via HTTP ; aucune probabilité ou estimation présentée comme revenu.

Les limites de déploiement S7/S8 persistent. S10 ne revendique ni nouvelle
recette production, ni nouvel exercice complet sauvegarde/restauration ou panne
PostgreSQL ; les preuves S7/S8 restent historiques.
