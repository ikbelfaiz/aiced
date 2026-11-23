# Démonstration Render : démarrage et diagnostic

Le `Dockerfile` racine exécute `python manage.py prepare_render`, puis Gunicorn.
Le démarrage est interrompu si PostgreSQL n'est pas configuré ou si une migration
échoue. Un verrou PostgreSQL sérialise l'initialisation entre les instances.
`preDeployCommand` n'est pas disponible sur une instance Render gratuite.

Dans Render, vérifier le service → **Environment** :

- `DATABASE_URL` : URL interne de la base PostgreSQL Render du projet ; secret.
- `DJANGO_SECRET_KEY` : secret aléatoire stable d'au moins 32 caractères.
- `DJANGO_DEBUG=0`.
- Pour une base de démonstration vide uniquement : `AICED_SYNTHETIC_DEMO=1`
  et `AICED_SEED_PASSWORD` aléatoire conforme (au moins 12 caractères).

Une création manuelle de service n'applique pas automatiquement `render.yaml`.
Le Blueprint lie ces variables ; sinon, configurer la base et ses variables dans
le tableau de bord. Ne jamais publier les URLs de connexion ou les mots de passe.
Laisser **Docker Command** vide pour utiliser le `CMD` du dépôt ; une surcharge
Gunicorn seule contournerait l'initialisation. Aucun changement de plan payant requis.

Après déploiement, rechercher « Base prête ; démarrage du serveur autorisé. »
dans les logs. Les seeds sont exécutés en une transaction uniquement si le mode
synthétique est explicite et qu'il n'existe ni compte, ni institution, ni client.
Une base existante est conservée sans réattribution de permissions. Les migrations
Django s'appliquent normalement. Ce chemin est réservé au service Render à base
unique, pas aux configurations Compose avec propriétés de schéma distinctes.

`GET /api/health/` est une sonde de vie, **pas une validation de PostgreSQL**.
Une réponse 200 de cette sonde ne prouve pas que la connexion fonctionne.
`GET /api/auth/csrf/` peut également fonctionner sans tables applicatives.

Pour une démonstration initialisée, le responsable synthétique
`synthetic.manager.a` utilise le secret `AICED_SEED_PASSWORD` de la première
initialisation. Un changement de variable ne réinitialise pas les comptes existants.
Le code d'institution de démonstration est `SYNTHETIC-A`. Un compte créé sur
`/inscription` reste inactif jusqu'à l'approbation dans `/administration/comptes` ;
ses habilitations doivent ensuite être attribuées explicitement.

Diagnostic du 23 novembre 2026 : page, sonde de vie et CSRF disponibles ; une
tentative de connexion fictive renvoie 500. La configuration gratuite utilisait
une commande pré-déploiement non supportée. La présence effective de `DATABASE_URL`
et l'état de la base distante restent à vérifier dans Render ; aucune donnée
réelle ni aucun compte n'a été créé par le diagnostic distant.
