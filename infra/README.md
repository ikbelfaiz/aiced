# Infrastructure locale

La configuration Compose est à la racine. Le port PostgreSQL n'est pas publié. Les serveurs de développement sont liés à 127.0.0.1 sur l'hôte. Volumes persistants pour PostgreSQL uniquement ; aucun document de référence dans les images. Ce socle n'est pas une configuration de déploiement production.
# Gateway M2

Le Compose principal publie seulement Nginx sur `127.0.0.1:5173`. Django, Vite et PostgreSQL restent internes. Ajouter une clé indépendante `AICED_GATEWAY_KEY` dans `.env`, partagée uniquement entre backend et Gateway. Configuration locale HTTP ; serveurs de développement existants conservés. Aucun changement de base ou de propriété des tables.

Voir [le guide M2](../docs/migration/m2-gateway.md) pour démarrage Docker/local, confiance IP/TLS, tests et rollback par `compose.direct.yaml`. Ne jamais utiliser `down -v` pour basculer. Docker/TLS de production doivent être vérifiés séparément.

