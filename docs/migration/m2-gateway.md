# M2 — Gateway transparent et MVP pragmatique

> S8 naming update: operational filenames in this guide use the [purpose-based mapping](../docker-compose.md). Reported milestone results are historical; original inventory JSON files retain their captured filenames.

> Nouvelle decision utilisateur apres M2 : cible a quatre services larges sur une instance/base PostgreSQL, schemas et credentials separes. Prospects et interactions appartiennent a Client & CRM. Le [plan de decomposition courant](coarse-services-plan.md) remplace les anciennes recommandations de ce document ; les preuves historiques M1/M2 restent conservees.

## Décision et périmètre

La dernière instruction utilisateur remplace la cible obligatoire à quatre services de l'audit initial : **le MVP recommandé est un monolithe modulaire Django/DRF/PostgreSQL derrière un Gateway Nginx**. Le Gateway est un processus/image déployable séparément, sans base ni logique métier. Aucune extraction de domaine, nouvelle table, migration, copie de données ou modification de propriété SQL dans M2. Les 38 routes du manifeste M1 restent dans `config/urls.py` ; aucune modification de `frontend/src/`.

Navigateur → Nginx → `/api/…` vers Django ; autres chemins vers React/Vite. Le port public Compose reste `http://localhost:5173`, donc origine, cookies, CSRF, routes SPA et appels relatifs existants restent compatibles. Backend et frontend ne publient plus de port dans la configuration par défaut ; PostgreSQL conserve son volume existant.

Sessions, révocation immédiate, rôles, scopes objet/organisation, contrôle financier, validation et audit transactionnel restent dans Django. Le Gateway ne décide jamais des droits et ne remplace pas les contrôles serveur. Les snapshots demeurent immuables ; aucune écriture Carthago, fusion d'identités/comptes ou synchronisation automatique n'est ajoutée.

## Configuration et sécurité

| Paramètre | Utilisation |
|---|---|
| `AICED_GATEWAY_KEY` | Secret indépendant, au moins 32 caractères ASCII URL-safe, identique dans Django et Nginx. Générer avec `python -c "import secrets; print(secrets.token_urlsafe(48))"` et conserver uniquement dans `.env` privé. Jamais dans React ou une URL. Vide dans Django = mode direct, aucun header de connexion accepté. |
| `GATEWAY_PORT` | Écoute interne Nginx, 8080 dans Compose. |
| `BACKEND_UPSTREAM` | `backend:8000` ; aucun changement de chemin API. |
| `FRONTEND_UPSTREAM` | `frontend:5173` ; SPA/assets/WebSocket HMR. |
| `BACKEND_TIMEOUT` | Délai d'inactivité de lecture d'amont, 120 secondes. Connexion 3 s, envoi 30 s ; aucun retry automatique, même pour POST/PATCH. |
| `DJANGO_ALLOWED_HOSTS` | Noms publics autorisés, sans port ; Host et Origin originaux sont conservés, pas remplacés par le nom du conteneur. |

Nginx remplace les headers privés `X-Aiced-*` et supprime les headers de forwarding publics. Django retire le secret avant de transmettre la requête aux vues et ne reconnaît IP/protocole qu'après comparaison constante du secret. Ce secret authentifie des métadonnées d'infrastructure, **pas un utilisateur**. Cela préserve le budget de login par IP et évite de croire un `X-Forwarded-For` arbitraire. Les connexions directes restent soumises aux sessions/CSRF et aux mêmes permissions.

Ne pas placer ce Gateway HTTP derrière un proxy TLS en supposant que `X-Forwarded-Proto` sera accepté : il est volontairement supprimé. Cette livraison est une configuration **locale de développement HTTP**. Pour la production, terminer TLS au Gateway et tester son `$scheme`, cookies Secure, redirections et CSRF réels ; ou définir et vérifier un autre contrat de proxy de confiance. Le secret d'infrastructure exige un réseau privé protégé ; une liaison inter-hôtes nécessitera TLS. Ne pas publier Django/Vite directement en production. Les serveurs Django runserver et Vite existants restent des serveurs de développement.

Limite globale 10 Mio, y compris upload binaire XLSX. Django conserve sa limite JSON indépendante de 64 Kio et tous ses contrôles fichier/contenu. Les erreurs Django (403/404/409/413/429, etc.), cookies multiples, téléchargements CSV et statuts 200/201/204 passent sans réécriture. Les erreurs propres au Gateway 413/502/504 ont l'enveloppe JSON `{error:{status,details}}`, texte français et `Cache-Control: no-store`. Aucun cache API. Les logs d'accès ne contiennent que statut/durée/statut d'amont ; aucun chemin, requête, corps, cookie ou clé. Le journal d'erreurs est limité au niveau critique ; les logs restent locaux au conteneur, pas un dispositif de supervision de production.

Nginx 1.30.6 est épinglé dans l'image et utilisé pour les tests locaux. La [page officielle des distributions](https://nginx.org/en/download.html) fournit les binaires ; `NGINX_BINARY` permet de choisir un binaire installé. Les exécutables téléchargés restent ignorés sous `.tools/`.

## Démarrage

Avec Docker disponible, renseigner `.env` à partir de `.env.legacy.example`, notamment les deux secrets distincts. Sur une installation existante, conserver exactement les paramètres PostgreSQL et le volume ; ne pas remplacer son mot de passe ou sa clé Django pour M2.

```sh
docker compose -f compose.legacy.yaml build
docker compose -f compose.legacy.yaml up -d
# Installation neuve uniquement : migrations habituelles, explicitement
docker compose -f compose.legacy.yaml exec backend python manage.py migrate
```

Ouvrir `http://localhost:5173` ; `/api/health/` doit répondre `{"status":"ok"}`. Ne pas exécuter de seed contre des données à préserver. Le démarrage ne lance aucune migration automatique.

Sans Docker : lancer Django sur 8000 et Vite sur 5173 selon le README, avec le même `AICED_GATEWAY_KEY` dans l'environnement du backend et du runner. Installer Nginx 1.30.6 sur PATH, ou définir `NGINX_BINARY` vers son exécutable absolu ; le runner reconnaît aussi `.tools/nginx-1.30.6/nginx.exe`.

```sh
python scripts/run_gateway.py --port 8080
```

Ouvrir `http://localhost:8080` ; Ctrl+C arrête seulement ce Gateway. `--env-file` accepte un fichier JSON privé contenant la clé partagée ; `--backend` et `--frontend` acceptent des adresses `hôte:port`. Les configurations rendues contenant la clé restent privées sous `.local/gateway/`. Ne pas lancer deux instances dans ce même répertoire.

## Désactivation et rollback

Aucune restauration, suppression de volume ou migration inverse n'est nécessaire : les écritures sont toujours dans la même base Django. Garder `DJANGO_SECRET_KEY`, cookies, host et port publics inchangés pour conserver les sessions. Les opérations en cours peuvent recevoir une erreur de connexion lors de l'arrêt ; vérifier leur état avant de les répéter. Le replay idempotent des imports reste assuré par le backend ; les autres mutations ne sont pas automatiquement rejouées.

```sh
docker compose -f compose.legacy.yaml stop gateway
docker compose -f compose.legacy.yaml -f compose.legacy-direct.yaml up -d db backend frontend
```

Le frontend reprend le port 5173 et relaie directement `/api` vers Django ; 8000 est publié uniquement en loopback pour le développement. Ne pas démarrer le service gateway avec cet override : son port entrerait en conflit. Pour revenir au Gateway, supprimer les ports directs par recréation avec le fichier principal :

```sh
docker compose -f compose.legacy.yaml -f compose.legacy-direct.yaml stop frontend backend
docker compose -f compose.legacy.yaml up -d --force-recreate backend frontend gateway
```

Ne jamais utiliser `down -v` ni réinitialiser PostgreSQL. En mode local sans Docker, ouvrir directement Vite sur son origine précédente et arrêter le Gateway ; pour conserver une session à travers un changement de processus, conserver la même origine publique. Le test HTTP de rollback réutilise réellement cookie et CSRF sur le même Host, modifie une note synthétique puis vérifie que logout invalide aussi l'accès direct.

## Vérification reproductible

```sh
python scripts/backend_check.py test core identity clients ingestion audit contracts --noinput
python scripts/backend_check.py test gateway_tests --noinput
python scripts/migration_baseline.py --confirm-synthetic --gateway
```

Les tests Gateway échouent explicitement si Nginx manque. Ils réutilisent les contrats consommateurs M1 avec de vraies sessions HTTP via Nginx ; aucune permission simulée. Le test de transport traverse chaque méthode déclarée des 38 routes du manifeste, vérifie chemin/query/corps/Host/Origin/cookies, 10 Mio exacts et dépassement, conflit sans réécriture, panne d'amont et timeout sans retry. Les tests Django vérifient aussi la confiance des métadonnées, le protocole TLS au niveau middleware et les rejets de métadonnées invalides. Les budgets login de sécurité utilisent les seuils normaux ; seuls les serveurs navigateur éphémères utilisent les seuils relevés habituels.

Le runner complet crée ses bases synthétiques marquées, migre/restaure, exécute tests et navigateurs DEV/bundle **via le Gateway**, compare les empreintes de la base locale existante avant/après et supprime uniquement ses bases temporaires. Rapports, mots de passe, dump et logs restent privés sous `.local/migration-baseline/<run>/`. Ce contrôle n'est pas une autorisation de migration de production.

Résultats du 14 novembre 2026, gate `--confirm-synthetic --gateway` terminé avec code 0 et statut `passed` :

| Vérification exécutée | Résultat |
|---|---|
| Backend PostgreSQL, dont contrats directs, isolation, révocation concurrente, imports et immuabilité | **100/100**, 43,423 s. |
| HTTP via Nginx réel, contrats consommateurs et transport | **10/10**, 68,455 s ; 38 chemins / 47 couples méthode-chemin traversés. |
| CSRF avant/après rotation, Origin interdit/autorisé, sessions et écriture après rollback direct | Nouveau contrôle ciblé réexécuté après ajout des assertions : **1/1**, 7,647 s. |
| Runner de sécurité M1, tests unitaires | **8/8**. |
| Chromium DEV via Gateway | **11/11**, y compris login/logout, révocation/expiration, refus IT, Client 360, prospects et imports. |
| Chromium bundle compilé via Gateway | **6/6**, 46,1 s. |
| TypeScript et build Vite | Succès. |
| Django check, migrations à jour, OpenAPI strict | Succès ; aucune migration à créer. |
| Backup/restore synthétique, session restaurée et neuf probes de contraintes | Parité exacte ; tous les rejets attendus vérifiés et annulés. |
| Base applicative existante | Empreintes données/schéma/séquences/ACL avant et après identiques. |
| Nettoyage | Deux bases de répétition supprimées ; aucune suppression de données applicatives. |

Rapport privé du gate : `.local/migration-baseline/46702da805a74ed9bf422467bad0dd6a/report.json`. Le test CSRF/rollback ciblé est aussi consigné dans `.local/m2-csrf-rollback.log`. Les premiers essais ont corrigé des problèmes du harness : fixtures non atomiques face aux contraintes différées, STATIC_URL absent du serveur de test et résolution IPv6 de localhost sur un listener IPv4. Les résultats ci-dessus proviennent des exécutions corrigées.

**Limites vérifiées :** Docker n'est pas disponible sur cette machine, donc aucun build/démarrage Compose ou rollback de conteneurs n'est déclaré testé. Les deux fichiers Compose ont été parsés ; le manifeste public de `nginx:1.30.6-alpine` répond HTTP 200. Le même template Nginx a été lancé réellement en processus local pour les contrats et navigateurs. Le protocole HTTPS est testé au niveau middleware, **pas par un vrai déploiement TLS**. TLS, serveur applicatif de production, supervision/rétention des logs et validation Docker restent à réaliser avant une mise en production.

## Après M2

Conserver les modules métier ensemble pour livrer le MVP : leur partage PostgreSQL protège actuellement les contraintes de sous-type, la révocation concurrente et les audits atomiques. Aucun besoin mesuré de scaling ou d'autonomie d'équipe ne justifie aujourd'hui le coût de séparation IAM/Client/Commercial. Prioriser les fonctionnalités AICED approuvées et l'exploitation du MVP. Les lots M3–M9 de l'audit deviennent des **options différées**, pas des prérequis au développement fonctionnel.

Réexaminer l'extraction de Data Integration seulement devant un besoin concret d'isolation de ressources, cadence de déploiement ou synchronisation read-only approuvée. Réutiliser alors les gates de backup, contrats, audit et révocation de l'audit avant toute nouvelle propriété de données. Reconciliation, Reporting et AI restent futurs et soumis à leurs règles métier approuvées ; pas de conteneurs vides ni de promesse d'architecture entièrement distribuée.

## Fichiers de cette tranche

| Fichiers | Changement |
|---|---|
| `infra/gateway/Dockerfile`, `nginx.conf.template`, `start.sh` | Nouvelle image et configuration Gateway, même template testé localement. |
| `compose.legacy.yaml`, `compose.legacy-direct.yaml`, `.env.legacy.example` | Entrée unique, secret technique, override de rollback sans modification du volume. |
| `backend/config/settings.py`, `backend/core/middleware.py` | Métadonnées du Gateway authentifiées ; autorisation et logique métier inchangées. |
| `backend/core/test_gateway_metadata.py`, `backend/gateway_tests.py`, `backend/testing/gateway.py` | Tests de confiance et harness réel Nginx/HTTP. |
| `backend/contracts/tests.py` | Réutilisation des mêmes contrats en direct et via HTTP ; normalisation UUID pour comparaison JSON. |
| `scripts/run_gateway.py`, `scripts/frontend_e2e.py`, `scripts/migration_baseline.py` | Démarrage local, option Gateway pour navigateurs et gate synthétique complet. |
| `README.md`, `infra/README.md`, `docs/architecture.md`, `docs/implementation-plan.md` | Démarrage et décision MVP actualisés. |
| `docs/migration/{current-architecture,target-architecture,service-boundaries,database-ownership,migration-plan,risks}.md`, `m2-gateway.md` | Statut courant, anciennes extractions explicitement optionnelles, configuration/rollback/preuves. |

Aucun fichier sous `frontend/src/`, modèle ou migration historique modifié. Aucun service métier ni nouvelle persistance créé.
