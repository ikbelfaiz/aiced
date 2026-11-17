# S12 — COM-04, agenda manuel personnel

## Fonction réellement livrée

`/agenda`, navigation « Agenda », affiche « Mon agenda » : calendrier mensuel,
compteurs par jour, sélection de jour, retour au mois ou à aujourd'hui et liste
chronologique paginée. Un utilisateur autorisé crée et modifie ses propres
rendez-vous : titre, date, heures de début/fin, type d'activité et notes facultatives.
Les types réutilisent les valeurs CRM `call`, `email`, `meeting`, `visit`.
Un appel peut représenter une relance ; l'email est une activité à préparer,
pas une livraison automatique.

L'inspection n'a trouvé aucun modèle de rendez-vous planifié. `Interaction`
enregistre un échange **réalisé**, interdit dans le futur, sans heure de fin.
Le nouveau `Appointment` est donc une planification Client & CRM, sans copie
d'interaction ni de prochaine action de prospect. Aucun lien dossier,
participant ou propriétaire secondaire n'est inventé ; la worklist S9 reste
distincte et aucune conversion/synchronisation n'est automatique.

Modèle provisoire autorisé : visibilité exclusive au créateur, même si ses
droits CRM portent sur l'organisation entière. Organisation et créateur sont
immuables ; le créateur vient uniquement de la session. Les droits existants
`clients.view` ∩ `interactions.view` sont nécessaires dans l'organisation ;
`interactions.manage` s'ajoute pour écrire. Les scopes assignés autorisent
uniquement cette planification personnelle, jamais les agendas des collègues.
Un lecteur peut voir ses rendez-vous sans pouvoir les modifier si le droit
de gestion a été retiré.

## Dates, heures et règles non approuvées

Les API de saisie reçoivent une date et deux heures locales `HH:MM` ; le serveur
les interprète selon `AICED_AGENDA_TIME_ZONE`, défaut **Africa/Tunis**, puis stocke
des instants PostgreSQL conscients du fuseau (UTC). Les réponses sont ISO 8601
avec décalage ; l'interface les affiche dans le fuseau métier retourné par le
serveur, indépendamment du fuseau navigateur. « Aujourd'hui » vient du serveur
converti dans cette zone, pas de son heure locale implicite.

Le fuseau est configurable par une zone IANA dans l'environnement privé,
validée au démarrage. Il n'est pas modifiable par la requête utilisateur.
Les heures inexistantes ou ambiguës lors d'un changement d'heure sont refusées.
Le MVP accepte une plage 1900–9998, à la minute, avec fin strictement après début
**sur la même journée**. Le multi-jour et la récurrence sont hors périmètre.
Un rendez-vous passé n'est pas automatiquement marqué réalisé ou transformé
en interaction.

Les chevauchements personnels sont **autorisés provisoirement**, avec mention
visible. Aucune règle d'exclusivité ou de participant n'est déduite. Annulation
indisponible, aucun DELETE public. Pas d'invitations, agenda d'équipe, email,
rappel, notification ou synchronisation. Ces extensions nécessitent les décisions
AMEN INVEST consignées dans `open-questions.md`.

## API additive

- `GET /api/agenda/` : mois courant métier par défaut ; paramètres `month=YYYY-MM`,
  `day=YYYY-MM-DD` (dans ce mois), `search` titre/notes (200 caractères),
  `page` ≥ 1, `page_size` 1–50, défaut 8. Tri `starts_at`, UUID.
- `POST /api/agenda/` : `organization_id`, `title`, `kind`, `date`, `start_time`,
  `end_time`, `notes` facultatif. `owner_id`, participants, champs inconnus et
  version de création sont refusés.
- `GET /api/agenda/context/` : organisations où le créateur peut écrire,
  fuseau métier et date métier. Aucun nom d'un autre utilisateur.
- `GET/PATCH /api/agenda/{appointment_id}/` : propriétaire autorisé seulement,
  sinon 404 (ou 403 si aucune capacité). PATCH partiel exige `version`, sinon
  conflit 409. Réorganisation/réattribution refusées.

La réponse de liste conserve l'enveloppe `count/next/previous/results` et ajoute
`days`, `month`, `business_timezone`, `business_date`. L'autorisation et le filtre
créateur précèdent recherche, compteurs, calendrier et pagination. Les cellules
portent sur le mois complet après recherche, avant sélection du jour. Les erreurs
masquent les données en cache. Aucun contrat historique n'est réécrit : 45 routes
publiques et 56 couples méthode/route avec les ajouts S8–S12.

## Migrations et sécurité

- `clients/0007_appointment` crée uniquement `clients_appointment`, index
  créateur/organisation/début, contraintes de durée et type, et trigger interdisant
  les changements d'ID/créateur/organisation.
- `iam_consumer/client_migrations/0009_appointment_refs` fusionne la nouvelle
  branche avec l'historique Client existant et pointe les deux FK sur les références
  **locales Client** `ActorRef`/`OrganizationRef`. La branche normale reste utilisée
  par les régressions isolées ; aucune ancienne migration n'est modifiée.
- `agenda_migrate.py` applique explicitement la migration Client comme tâche de
  déploiement, uniquement sur la base marquée synthétique `aiced_s7_disposable`.
  L'initialiseur Compose l'appelle avant le démarrage des services, sans réimport
  ou réensemencement des données existantes. Les GRANT/REVOKE de la seule nouvelle
  table sont atomiques. Client reçoit SELECT/INSERT/UPDATE ; pas DELETE. Aucun
  transfert d'ownership, rôle nouveau, schema voisin ou fichier Compose modifié.

Les écritures verrouillent l'organisation puis utilisent l'admission existante
avec révocation IAM fraîche, verrou de rendez-vous et contrôle de version.
Appointment, audit et outbox Client sont transactionnels. Un défaut d'outbox annule
la création. Les autres services ne peuvent pas lire la table ; la base empêche
la réattribution même avec le credential runtime Client. L'audit conserve ses
autorisations historiques et n'enregistre pas le titre/les notes dans le contexte.
La désactivation d'un utilisateur ne supprime pas ses rendez-vous.

## Recette Docker réelle — 15 novembre 2026

Docker Engine 29.9.3 / Compose v5.7.0, stack isolée `aiced-test`, navigateur →
Nginx → Client/IAM → PostgreSQL. Aucun serveur local de remplacement.

| Vérification | Résultat final |
|---|---|
| Régression générale backend | 166 tests réussis, dont 6 nouveaux S12 |
| IAM / Integration / Commercial propres | 5 / 8 / 7 réussis ; total backend **186** |
| Chromium compilé | **24 réussis**, 1 ignoré (maquettes réservées au développement), aucun échec final |
| Trois scénarios Agenda | Saisie/validation/édition/calendrier/jour/mois/rechargement/mobile ; chevauchement conservé ; erreur masquant calendrier/liste puis reprise ; refus IT |
| Fuseau navigateur | America/Los_Angeles ; saisie et affichage restent en Africa/Tunis |
| Sondes réelles S12 | 4 contrôles : propriétaire malgré droits d'organisation ; PATCH simultanés 200/409 et deux paires audit/outbox (création + une édition) ; ACL/FK locales/trigger ; utilisateur réellement désactivé refusé en lecture/écriture |
| Redémarrage du seul Client | Même session, lignes/versions/compteurs/cellules identiques ; trois pairs inchangés |
| Sondes historiques quatre services | 15 contrôles : isolation SQL, révocation/concurrence, signature/rejeu, rollback audit/outbox, livraison dédupliquée et audit fédéré |
| API/OpenAPI | Contrats historiques compatibles, ajouts revus ; 45 routes/56 couples méthode-route, anonyme et routes retirées refusés |
| Migrations | Appliquées dans l'initialisation ; contrôle Client `makemigrations --check --dry-run` sans dérive, `migrate --check` réussi ; réexécution explicite sans migration à appliquer |
| Compose | Parité des 8 configurations et séparation test des volumes/credentials ; 7 conteneurs sains et quatre processus Django distincts |

Les tests nouveaux ont d'abord échoué en 404 avant les endpoints. Une assertion
initiale de test attendait une chaîne UTC, alors que la réponse ISO 8601 portait
correctement `+01:00` ; elle compare désormais l'instant normalisé. Trois anciens
scénarios Clients supposaient une seule ligne visible, hypothèse invalidée par
les fixtures S11 conservées. Ils ciblent maintenant leur dossier synthétique
de référence et vérifient aussi la suppression du filtre à la réinitialisation.
Aucune donnée n'a été supprimée et aucune permission élargie pour faire passer
ces tests. La suite complète finale passe après reconstruction finale.

Les six tests backend couvrent propriétaire caché, organisation étrangère,
forçage de créateur, IT/anonyme/révocation, dates et heures invalides, DST ambiguë
ou inexistante avec une zone alternative, overlaps/adjacence, pagination, version
obsolète, immutabilité et rollback d'outbox. La capture mobile a été inspectée.
Les données de navigateur/sondes sont explicitement synthétiques et conservées
dans la base jetable avec leur historique ; les rôles de sonde sont retirés.

```powershell
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.test.yaml restart gateway
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
python scripts/compose_browser.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/agenda.py
python scripts/compose_agenda_restart.py --test
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
python scripts/compose_validate.py
python scripts/compose_inventory.py --test
```

Les sondes qui révoquent un utilisateur et les redémarrages s'exécutent après
les suites navigateur, pas en parallèle. Les rapports privés restent sous
`.local/compose-test/`. La migration et les ACL ont été vérifiées sur la stack
existante ; aucune nouvelle recette de cluster vierge complet ou sauvegarde/
restauration n'est revendiquée pour S12.

## Fichiers de l'incrément

- Backend : `clients/models.py`, `clients/agenda.py`, `clients/tests_agenda.py`,
  `clients/migrations/0007_appointment.py`,
  `iam_consumer/client_migrations/0009_appointment_refs.py`, `config/settings.py`,
  `config/urls.py`, `contracts/additions.py`, `service_architecture/ownership.py`
  (sous `backend/`).
- Frontend : `features/agenda/AgendaPage.tsx`, `app/App.tsx`,
  `components/layout/AppShell.tsx`, `workspace.css` (sous `frontend/src/`),
  `frontend/e2e/agenda.spec.ts`, `frontend/e2e/screens.spec.ts`.
- Validation/déploiement : `infra/acceptance/agenda_migrate.py`, `bootstrap.py`,
  `agenda.py`, `routes.py`, `verify.py`, `scripts/compose_agenda_restart.py`.
- Documentation : ce rapport, `docs/mvp-backlog.md`, `docs/functional-gap-analysis.md`,
  `docs/open-questions.md`, `docs/docker-compose.md`,
  `docs/s11-pipeline-limit-remediation.md`.

Les modifications S7–S11 déjà présentes sont conservées. Pas de nouveaux services,
accès Carthago, données financières, credentials ou fichiers Compose.

## Limites et prochaine étape

Les politiques d'équipe/participants, annulation, récurrence, multi-jour,
notification et synchronisation restent bloquées ou hors périmètre. Owner-only,
chevauchements autorisés et zone par défaut sont explicitement provisoires.
Les limitations de déploiement S7/S8 persistent : la recette locale ne démontre
pas la préparation à la production.

La limite S11 reste active. Son [plan séparé](../s11-pipeline-limit-remediation.md)
définit benchmark, contrat signé paginé, compteurs exacts et tests de révocation,
sans migration d'architecture. Prochain incrément technique recommandé : réaliser
ce plan après benchmark/revue ; obtenir en parallèle les décisions AMEN INVEST
avant d'étendre l'agenda ou d'entamer des campagnes.
