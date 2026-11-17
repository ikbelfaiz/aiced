# Infrastructure locale AICED

`compose.yaml` démarre la stack acceptée à quatre services Django. `compose.dev.yaml`
change uniquement le mode frontend ; `compose.test.yaml` isole le projet, les
credentials, le port et le volume des essais. Aucun déploiement production fourni.

`gateway/` porte Nginx, son routage explicite et ses contrôles de métadonnées.
`acceptance/` contient le job offline d'initialisation synthétique et les sondes
de contrat, isolation, audit, import et historique. Le chemin interne `/s7`
reste inchangé pour préserver les commandes des conteneurs ; seul le nom du
répertoire hôte devient descriptif.

Voir [les commandes et le mapping historique](../docs/docker-compose.md).
Les anciens overlays sont réservés aux migrations/reprises documentées, jamais
à une bascule par `down -v` ni à un démarrage parallèle sur un volume métier.
