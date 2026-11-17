# S14 — COM-05 : brouillons manuels de campagnes

## Périmètre livré

`/campagnes`, entrée « Campagnes » : liste personnelle, création, consultation et
modification. Nom obligatoire (160), description (5 000), début/fin prévus
facultatifs et notes de préparation du ciblage (2 000). Recherche nom/description/
notes, tri déterministe avec UUID, pagination 8 par défaut / 50 maximum.
L'interface réutilise les cartes, filtres et éditeur AICED. Capture mobile
inspectée, sans débordement ; aucune fidélité à une maquette non inspectée revendiquée.

Un brouillon reste **draft**, sans transition, activation, suppression, envoi,
notification, audience, participant ou responsable métier. Activation et envoi
sont désactivés. Les notes de ciblage sont du texte non exécuté : aucun segment,
identifiant client, affectation, effectif ou requête client n'est créé. Le
ciblage et la communication ne sont donc pas des fonctionnalités livrées.
Le créateur constitue une garde technique personnelle provisoire, sans règle
d'ownership commercial approuvée. Aucun autre créateur n'accède au brouillon,
même avec un grant organisationnel dans la même organisation.

## Autorisation, temps et transactions

- Aucun rôle/grant attribué automatiquement. Autorisation provisoire :
  `opportunities.view` pour ses brouillons, intersection dans la même organisation
  avec `opportunities.manage` pour écrire. Les deux scopes IAM existants
  n'autorisent que cette préparation personnelle, jamais une audience/clientèle.
  Une matrice propre aux campagnes reste à approuver.
- Snapshots IAM signés et frais, barrières existantes de révocation jusqu'à la
  fin de transaction, revalidation avant exposition/sauvegarde. IT sans accès
  implicite. Créateur + organisations autorisées filtrent avant recherche,
  compte, tri, page et détail. Perte de manage : lecture personnelle seule ;
  révocation de view/utilisateur/session : accès fermé.
- Organisation et créateur immuables. `owner_id`, `client_ids`, `segment_id`,
  `recipients` et `status` sont refusés. Aucune référence client ne nécessite
  de nouvel appel Client ; toute future référence devra être autorisée et
  revalidée par Client. Les notes ne donnent aucun droit et ne sont pas un mapping.
- PATCH : version courante obligatoire, verrou de ligne, incrément et conflit
  409. Longueurs, nom non vide, dates ISO et fin >= début lorsque les deux sont
  présentes, y compris en modification partielle. Dates passées et dates uniques
  admises pour la préparation ; aucune règle de clôture/délai inventée.
- Dates prévues civiles, sans conversion UTC ou changement selon le navigateur.
  `AICED_COMMERCIAL_TIME_ZONE` configure le contexte de date métier et le fuseau
  Commercial ; défaut `Africa/Tunis`, valeur IANA invalide refusée au démarrage.
  Réglage facultatif dans l'environnement privé Commercial, sans changement
  Compose ; confirmation métier attendue. Horodatages stockés comme instants.
- Mutation, journal `commercial.campaign_draft_saved` et outbox dans la même
  transaction. L'enveloppe d'audit exclut nom/description/notes. IAM autorise
  **cet événement exact uniquement depuis Commercial** ; aucun préfixe libre
  n'est ajouté. Déduplication des reçus et reprise après accusé perdu conservées.

## API additive et migration

| Route | Méthodes | Fonction |
|---|---|---|
| `/api/campaigns/` | GET, POST | Mes brouillons autorisés / création |
| `/api/campaigns/context/` | GET | Organisations où créer, fuseau/date |
| `/api/campaigns/{campaign_id}/` | GET, PATCH | Mon brouillon / édition versionnée |

GET : `search`, `ordering` (`±name`, `±updated_at`, `±planned_start`), `page`,
`page_size`. Champs éditables : `name`, `description`, `targeting_notes`,
`planned_start`, `planned_end` ; `organization_id` seulement à la création,
`version` au PATCH. Sortie : statut constant, créateur, horodatages et `can_edit`.
Les routes/schémas antérieurs restent inchangés. Nginx route ces chemins
exclusivement vers Commercial. Les vues de contrat Client exposent OpenAPI mais
échouent sans Commercial, sans persistance locale ni monolithe de secours.
Additions revues dans `backend/contracts/additions.py`, baseline intacte.

Migration **`commercial_store/0003_campaign_draft.py`** : seule nouvelle table
`aiced_commercial.commercial_store_campaigndraft`, FK ActorRef Commercial,
index créateur/organisation/date, contraintes draft/version/dates ; triggers
identité/créateur/organisation/date de création immuables et gate Commercial.
Aucun transfert ou relation Client/IAM. `infra/acceptance/campaign_migrate.py`,
appelé explicitement par initialize avant les services, utilise le propriétaire
Commercial existant. Runtime : SELECT/INSERT/UPDATE, sans DELETE, DDL, TEMP ou
credential migrateur ; les trois autres services ne lisent pas la table.
Le script refuse toute base autre que le cluster Docker jetable marqué
synthétique. Une migration production nécessite une procédure approuvée
distincte ; ne pas supprimer la table pour revenir à un ancien frontend.

## Recette Docker

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/campaigns.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
python scripts/compose_browser.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_campaign_restart.py --test
python scripts/compose_inventory.py --test
python scripts/compose_validate.py
```

Révocation/rollback/pannes séquentiels, sans navigateur concurrent. Régressions
Django dans leur propre base transitoire. Les brouillons synthétiques et audits
sont conservés ; grants temporaires retirés et utilisateur restauré. Aucun
import réel ni appel Carthago. S13 peut être activé avec `AICED_E2E_SCALE=1`
si son jeu synthétique existe ; voir sa recette. Rapports exclus dans
`.local/compose-test/` : `campaigns-report.json`, `campaign-restart-report.json`,
`regression-report.json`, `*-tests.log`, `browser-compiled/report.json`,
`integration-report.json`, `routes-report.json`, `container-inventory.json`.

## Résultats réels — 15 novembre 2026

- Docker Engine **29.9.3**, Compose **v5.7.0** : sept conteneurs applicatifs
  sains dans `aiced-test`, quatre processus Django distincts, PostgreSQL privé.
  Une indisponibilité du moteur Desktop a été observée pendant la recette ;
  relance, reprise sur les volumes conservés et vérification finale réussies.
- **200 tests backend réussis** : 169 socle/Client/contrats, 5 IAM,
  8 Integration, 18 Commercial. Les six tests unitaires campagnes ont aussi
  été rejoués après renforcement des assertions de validation : réussis.
- **28 scénarios Chromium réussis, 1 ignoré** (référence visuelle du mode
  développement), dont trois nouveaux scénarios campagnes et le scénario S13
  activé à 10 000 opportunités. Fuseau navigateur America/Los_Angeles pour les
  campagnes ; dates civiles Tunis inchangées. Capture mobile inspectée.
- **7 groupes de probes campagnes réussis** : isolation créateur/org/IT,
  validations/champs interdits/CSRF/pagination, deux PATCH concurrents 200/409,
  rollback journal/outbox forcés, ACL et contraintes DB, livraison signée sans
  contenu et rejeu dédupliqué, retrait manage/rôle/utilisateur/session avec
  refus de modification après désactivation.
- **15 probes d'intégration existantes réussies**, y compris audit fédéré,
  isolation des quatre credentials et historiques, révocation et rollback.
  **48 routes / 61 méthodes-chemins** : compatibilité OpenAPI antérieure et
  refus des opérations anonymes vérifiés. Le premier passage avait détecté le
  nouvel événement absent de l'allowlist IAM : ajout exact, test de domaine et
  déduplication, puis régression relancée avec succès.
- **2 scénarios de reprise réussis** : seul Commercial redémarré, trois pairs
  inchangés et mêmes brouillons/versions/dates/session ; IAM réellement arrêté,
  lectures et écritures fermées, puis contenu identique après récupération.
- `makemigrations --check --dry-run` : aucune dérive. Huit configurations
  Compose conservées : contrôle de compatibilité et séparation main/test réussi.
  `git diff --check` : aucune erreur de whitespace.

La stack locale principale a aussi été mise à jour sans réensemencement :
`http://127.0.0.1:5187/campagnes`. Page, GET liste et contexte authentifiés :
HTTP 200 ; sept conteneurs sains. La recette complète et les mutations de test
ont été exécutées sur **le projet isolé**, port 5188, pas sur la base principale.
Aucune donnée privée ou réelle importée. Aucun échec dans les exécutions finales.

## Fichiers de l'incrément

- Commercial : `commercial_store/models.py`, migration `0003_campaign_draft.py`,
  `commercial/campaign_contract.py`, `commercial_service/campaigns.py`,
  `settings.py`, `urls.py`, `tests_campaigns.py`.
- Contrats/routage : `config/urls.py`, `contracts/additions.py`,
  `service_architecture/ownership.py`, `infra/gateway/nginx.conf.template`.
- Audit : `internal_api/views.py`, `internal_api/tests.py`, `audit/services.py` ;
  seul l'événement exact de sauvegarde est ajouté au domaine Commercial.
- Frontend : `features/campaigns/CampaignsPage.tsx`, `app/App.tsx`,
  `components/layout/AppShell.tsx`, `e2e/campaigns.spec.ts` ; `e2e/screens.spec.ts`
  attend aussi la liste remise à zéro avant de saisir un nouveau filtre,
  sans assouplir le compte attendu du client synthétique.
- Initialisation et probes : `infra/acceptance/bootstrap.py`,
  `campaign_migrate.py`, `campaigns.py`, `scripts/compose_campaign_restart.py`.
- Ce rapport, analyse fonctionnelle, backlog MVP, questions ouvertes et guide
  Compose. Aucun fichier Compose YAML, credential ou ancien historique modifié.

## Décisions AMEN INVEST et suite

À approuver : matrice campagnes ; propriétaire métier, affectation/partage ;
statuts/transitions, approbation, activation/annulation/rétention ; critères et
cibles clients/prospects, consentement/exclusions ; canaux, destinataires,
contenus/rappels ; attribution des résultats et KPI ; fuseau final.

Suite : cadrage puis sélection **manuelle explicite** de cibles, autorisées et
revalidées par Client à chaque action, après approbation des règles. Aucun calcul
automatique, lancement ou transport avant ces décisions. Les autres écarts
restent dans le backlog. Ce MVP ne termine pas le module Commercial et ne
constitue pas une recette de production.
