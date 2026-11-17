# AICED

CRM AMEN INVEST : Panorama Clients, Pilotage Commercial et Pilotage Managérial.
Architecture gelée : React → Nginx → quatre services Django (IAM, Client & CRM,
Commercial, Data Integration), PostgreSQL avec schémas et credentials restreints.
Carthago reste en lecture seule ; aucun connecteur réel ou mapping non approuvé.

## Démarrer la stack locale

Prérequis : Docker Engine/Compose récent (`!override` nécessite Compose 2.24.4+),
Python pour générer les configurations privées. Aucune base locale requise.

```powershell
# Une seule fois ; refuse de remplacer des credentials existants.
python scripts/compose_prepare.py
docker compose up --build -d --wait --wait-timeout 180
docker compose ps --all
```

Application compilée : <http://127.0.0.1:5187>. Les comptes `synthetic.*` sont
explicitement fictifs. Mot de passe généré dans `.local/s7/config.json`, jamais
affiché par les scripts. Si la configuration S7 existe déjà, ne pas régénérer :
le projet, les secrets, le volume et les données sont conservés. Initialisation
et migrations précèdent les serveurs ; aucun backend monolithique dans la stack.

Pour développer le frontend en conservant les quatre services Docker :

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait
docker compose restart gateway
```

La configuration locale est synthétique, en DEBUG et HTTP à l'entrée navigateur.
Elle n'est pas une configuration de production. Aucune `compose.prod.yaml`
supportée n'existe.

## Tests isolés

```powershell
python scripts/compose_prepare.py --test
docker compose -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
python scripts/compose_validate.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/regression.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/verify.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/history.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/routes.py
docker compose -f compose.yaml -f compose.test.yaml run --rm --no-deps initialize python /s7/imports.py
python scripts/compose_browser.py --test
python scripts/compose_history_restart.py --test
python scripts/compose_inventory.py --test
```

Stack de test : <http://127.0.0.1:5188>, projet, credentials et volume distincts.
Ne pas changer son nom de projet, réutiliser les secrets de l'application ou
lancer un runner contre une base réelle. Les tests navigateur utilisent Node et
Chromium installés côté hôte ; ils ne lancent aucun serveur de développement local.
Les prérequis détaillés et commandes de reprise sont dans le
[guide Compose](docs/docker-compose.md).

## État fonctionnel et suite

Répertoire, fiche CRM, prospects, interactions/opportunités par fiche et snapshots
d'import disposent de parcours réels. L'historique transversal est le premier
incrément S8. Agenda, campagnes, segmentation complète, KPI managériaux et IA ne
sont pas déclarés complets. Les valeurs graphiques d'aperçu sont fictives et
exclues du build compilé. Les estimations d'opportunité ne sont pas des encours.

- [Analyse validée des trois modules](docs/functional-gap-analysis.md)
- [Backlog MVP et critères d'acceptation](docs/mvp-backlog.md)
- [Résultats S8](docs/migration/s8-functional-validation.md)
- [Sécurité](docs/security-model.md) et [décisions métier attendues](docs/open-questions.md)
- [Recette Docker S7](docs/migration/s7-compose.md)

Les configurations de migration/rollback sont conservées sous des noms explicites
et ne sont jamais empilées sur la stack courante. Le
[mapping historique](docs/docker-compose.md) conserve leurs anciens noms ; le
[README antérieur](docs/history/README-before-default-compose.md) est archivé.
Les extractions privées, secrets, uploads et captures restent exclus de Git.
