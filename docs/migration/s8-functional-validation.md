# S8 — validation fonctionnelle et premier incrément MVP

**Périmètre S8 exécuté et vérifié sur données synthétiques Docker, le 15 novembre
2026.** La recette AMEN INVEST et la production ne sont pas déclarées acquises.

## Périmètre

S7 accepté provisoirement ; architecture gelée à quatre services. Aucun service
extrait, aucune table transférée, aucune propriété restructurée. Le périmètre
fonctionnel est corrigé en trois modules métier, distincts des services :
[analyse des écarts](../functional-gap-analysis.md) et [backlog détaillé](../mvp-backlog.md).
Les spécifications AICED p.5–8 et le cahier §§5–7 ont été relus, puis comparés
au code, modèles et APIs. La maquette PDF 09 a été rendue et inspectée avant
construction de l'écran d'historique ; aucune fidélité pixel exacte n'est annoncée.

## COM-01 — historique transversal des interactions

Nouvel écran `/interactions`, accessible depuis la navigation sur habilitation.
Lecture réelle `GET /api/interactions/` chez Client & CRM, propriétaire actuel
des interactions. Les créations/éditions restent sur les routes de fiche et
services transactionnels existants. Aucune migration nécessaire : le modèle
Interaction et les références locales suffisent ; drift et migrations vérifiés.

- Recherche serveur sur nom du dossier, objet et compte rendu ; type, dates
  inclusives du calendrier Africa/Tunis, identifiant de dossier/auteur en API.
- Pagination stable par date puis UUID, tailles 1–50, validation des filtres et
  bornes. L'UI expose recherche/type/dates/taille/page ; pas de sélecteur global
  d'auteur ni de catalogue non autorisé.
- Intersection `clients.view` et `interactions.view` sur le même dossier, y
  compris scope `assigned`. `prospects.view` demeure requis pour un prospect.
  Filtrage avant count/search/page ; révocation IAM prise en compte à la requête.
- Table et compte rendu, auteur de saisie explicitement identifié, date Tunis,
  lien vers la fiche, états chargement/vide/erreur/interdit et rendu mobile.
  Aucun solde, score, résultat commercial ou contact effectif déduit des notes.
- Un utilisateur IT ou anonyme ne reçoit aucune ligne. Les clés de cache sont
  rattachées à l'utilisateur et la sélection ; pas de réutilisation de lignes
  après un refus. L'authentification et les mutations CSRF ne sont pas modifiées.

Les six tests d'isolation ont été écrits et exécutés avant l'endpoint (échec
attendu sur route absente), puis passent après implémentation. Quatre sondes
réelles complètent les tests ORM : IAM distant, affectations, IDs inter-objets/
organisations, classification prospect et révocation. Les fixtures des sondes
sont synthétiques, temporaires et nettoyées ; aucun enregistrement client réel
importé. Deux nouveaux scénarios Chromium parcourent l'application réelle ; un
troisième injecte une erreur 503 pour vérifier disparition des anciennes lignes
en cache et reprise sur l'API réelle. Ce troisième test ne remplace pas les
coupures réelles de conteneurs, exécutées séparément par le runner de reprise.

La maquette montre aussi des métriques, résultats d'interaction, prochaine action,
types note/rendez-vous séparés et filtres commerciaux plus riches. Ces fonctions
ne sont pas déclarées livrées par COM-01. L'auteur n'est pas assimilé à un
commercial affecté. Agenda, campagnes, portefeuille et KPI restent au backlog.

## Compatibilité et nommage Docker

La [table ancien → nouveau](../docker-compose.md) couvre huit fichiers Compose,
deux Dockerfiles, le template legacy, la configuration Vite et les runners.
La stack principale est maintenant `compose.yaml`, vérifiée avec la commande
standard `docker compose up --build -d --wait`. Les noms de projet, image Python,
volume, ports, credentials et chemins privés existants sont conservés. Aucun
overlay de reprise n'est supprimé car il reste requis par la documentation
historique ; les snapshots/manifests capturés ne sont pas réécrits.

`compose.test.yaml` ajoute seulement l'isolation des essais : autre projet,
volume PostgreSQL explicite, réseau, credentials/certificats et port 5188.
Il ne modifie pas le comportement de la stack principale sur 5187. Aucune
configuration production n'est inventée. README, guides, commandes de démarrage,
retour arrière et scripts sont mis à jour ; aucun CI/CD existant à modifier.

Les 38 routes / 47 méthodes historiques et leurs composants OpenAPI restent
identiques à la référence gelée. `contracts/additions.py` déclare uniquement
`GET /api/interactions/` et ses deux composants ; toute autre différence échoue.
Le total courant est **39 routes / 48 couples méthode-chemin**. Les anciens
hashes de migration et le JSON de référence ne sont pas modifiés. Les gates de
reprise S6 conservent ce contrôle de compatibilité plutôt qu'une régénération
de référence depuis le candidat.

## Vérifications exécutées

Docker Engine **29.9.3**, Compose **v5.7.0** disponibles. L'initialisation de la
base de test distincte et le démarrage de ses sept conteneurs ont été exécutés,
pas seulement la validation YAML. L'application principale est également
démarrée par le point d'entrée par défaut, avec données/volume conservés.

| Vérification | Résultat |
|---|---|
| Parité des configurations renommées | 8 configurations comparées par Compose à la référence issue des anciens fichiers ; comportement conservé |
| Isolation application/test | Noms de projets/volumes et credentials distincts vérifiés dans les configurations effectives ; aucun port DB publié |
| Backend régression/contrats | **145 tests passés**, dont 6 nouveaux tests d'historique, sur base Docker de test temporaire |
| Services indépendants | IAM **5**, Integration **8**, Commercial **5** passés — total backend **163** |
| Sondes quatre services | **15 contrôles passés** : isolation LOGIN, révocation/concurrence, TLS/signatures/rejeu, rollback audit/outbox, déduplication receipts, audit fédéré |
| Historique réel via Nginx/IAM | **4 contrôles passés** : scopes/compteurs, IDs interdits, prospects et révocation immédiate |
| Contrats HTTP | 39 routes / 48 méthodes contrôlées, 38 routes historiques OpenAPI inchangées |
| Imports | **5 contrôles passés**, XLSX/rejets/CSV, revue distincte, publication immuable et replay idempotent |
| Chromium test compilé | **14 passés**, 1 test réservé au mode développement ignoré |
| Chromium application par défaut | **14 passés**, 1 test réservé au développement ignoré |
| Chromium test développement | **14 passés**, 1 test réservé au build compilé ignoré |
| Pannes/restauration avec runner renommé | IAM/Client/Commercial/Integration/PostgreSQL, sessions et reprise passés ; dump restauré vers une autre base jetable, 81 tables identiques et ACL effectives vérifiées |
| Persistance du nouvel historique | Même session et mêmes lignes/compteurs après redémarrage Client seul ; PID Client remplacé et trois pairs inchangés |
| Build et migrations | TypeScript/Vite et images construits ; `makemigrations --check --dry-run` : aucun changement ; `migrate --check` : à jour |

Résultats finaux : **163 tests backend et 42 exécutions navigateur applicables
réussis**, zéro échec final ; trois exclusions liées au mode. Les tests de
parité, sondes HTTP/SQL, import, pannes et restauration ci-dessus sont comptés
séparément. Les sept conteneurs de chaque projet sont sains ; les deux frontends
finaux servent le build compilé. Référence visuelle PDF inspectée avant écran,
capture mobile réelle inspectée après recette ; table horizontalement défilante,
aucune métrique fictive ou fidélité pixel exacte revendiquée.

Rapports privés dans `.local/compose-test/`, `.local/s7/` et `.local/s8/` :
régressions, sondes, navigateurs, inventaires et comparaison de configurations.
Le premier essai navigateur a révélé une ambiguïté de libellé accessible du
sélecteur ; corrigée dans l'UI et rejouée sans affaiblir les assertions. Les
échecs intermédiaires ne sont pas comptés comme des succès finaux.

## Limites et prochain incrément

Recette synthétique locale, pas production : DEBUG/HTTP à l'entrée, serveurs de
développement/preview, secrets/certificats temporaires, budgets de tests relevés.
Pas de validation de charge, SSO/MFA, recette métier ou certification visuelle.
Le restore utilise le cluster jetable avec ses rôles existants, pas un sinistre
sur cluster vierge. Nginx exige un redémarrage après recréation avec changement
d'IP, comportement déjà documenté à S7.

**Suite recommandée : COM-02**, worklist des prochaines actions de prospects
déjà saisies, avec dates explicites et contrôle de périmètre, sans notifications
automatiques. AMEN INVEST doit approuver les règles d'agenda partagé, résultats/
contact effectif, catalogue/affectations/conversion, canaux/consentements, mapping
source et matrice/formules des KPI direction. Le Pilotage Managérial demeure
largement manquant ; il n'est pas annoncé complet par l'écran de dashboard.
