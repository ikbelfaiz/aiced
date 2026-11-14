# Bilan Phase 1 — fondations backend et sécurité

Ce bilan conserve les résultats de la livraison initiale (46 tests). La revue critique et ses corrections ultérieures sont consignées dans `phase-1-review.md` (64 tests PostgreSQL et vérification HTTP du proxy).

## Périmètre livré

- Django REST Framework, PostgreSQL et migrations des organisations, capacités, rôles, memberships, grants avec scope/expiration, budget de connexion et audit.
- Modèles clients fondamentaux : Party, sous-types physique/moral, profil CRM séparé, identité externe et projection minimale de compte local en lecture seule. Pas de solde, d'encours ou de calcul financier.
- Sessions Django : connexion/déconnexion CSRF, rotation de session et jeton, password validation/hashing, révocation effective aux requêtes suivantes, découverte des propres accès.
- Autorisation explicite par capacité et organisation, scope `assigned` ou `organization`, aucun héritage implicite vers les sous-organisations, aucun contournement Django staff/superuser/Group.
- Lecture clients bornée et paginée, détail objet, modification de notes CRM allowlistée et lecture de comptes exigeant une habilitation financière distincte. Les mêmes contrôles sont réappliqués dans les services.
- Administration limitée à la création de comptes sans privilèges, état du membership et attribution/révocation des rôles existants. Aucun rôle ou flag privilégié modifiable par payload arbitraire. Délégation conservatrice sans auto-attribution, élargissement d'autorité ou prolongation des droits.
- Audit durable des accès refusés, CSRF, connexions/échecs/throttling/déconnexions, créations de comptes et changements d'habilitations. Snapshots contrôlés avant/après des permissions ; aucun credential ou contenu de note. Audit et mutation dans la même transaction.
- Triggers PostgreSQL d'audit append-only, intégrité de sous-type, interdiction de réaffectation d'une identité de sous-type et FK composite interdisant un gestionnaire d'une autre organisation.
- Budget de connexion PostgreSQL partagé et verrouillé, clés HMAC par compte/IP, réponse générique de credentials invalide. Réponses API no-store et identifiant de corrélation généré serveur.

## Fichiers créés ou modifiés

| Zone | Fichiers principaux |
|---|---|
| Identité | `backend/identity/models.py`, `policies.py`, `services.py`, `authentication.py`, `serializers.py`, `views.py`, migration `0002_*`, `management/commands/seed_synthetic.py`, `tests.py` |
| Clients | `backend/clients/models.py`, `serializers.py`, `services.py`, `views.py`, migrations `0001` à `0003` |
| Audit | `backend/audit/models.py`, `services.py`, `views.py`, migrations `0001` à `0003` |
| Configuration | `backend/config/settings.py`, `urls.py`, `backend/core/serializers.py`, `middleware.py`, `errors.py`, `backend/requirements.txt`, `requirements.lock`, `.env.example` |
| Vérification | `scripts/local_postgres.py`, `scripts/backend_check.py`, `.github/workflows/ci.yml` |
| Documentation | `README.md`, `docs/architecture.md`, `database-design.md`, `security-model.md`, `implementation-plan.md`, `open-questions.md`, ce bilan |

Les fichiers frontend et les adaptateurs ingestion n'ont pas été modifiés pendant cette phase.

## Environnement et données

PostgreSQL 17.11 Windows téléchargé via le [distributeur EDB référencé par PostgreSQL](https://www.postgresql.org/download/windows/) et exécuté dans un cluster isolé sous `.local/postgres/`, lié à `127.0.0.1:55432`. Aucun service Windows installé. Les scripts de vérification utilisent ce cluster, pas une base métier existante. Secrets générés localement dans des fichiers ignorés, jamais reproduits dans ce bilan.

Le seed explicite a été exécuté deux fois : 2 organisations, 6 utilisateurs, 2 clients, 2 comptes `SYNTHETIC_ONLY`, 6 grants. Replay sans duplication ni remplacement des mots de passe. Le seed refuse DEBUG=0 ou l'absence de `--confirm-synthetic`. Les rôles `synthetic-reader`, `synthetic-manager`, `synthetic-it` sont démonstratifs exclusivement. Aucun document de référence ni donnée réelle importé.

## Vérifications

Commandes locales : `python scripts/backend_check.py migrate --noinput`, `check`, `makemigrations --check --dry-run`, `test core identity`, `spectacular --file .local/phase1-schema.yaml --validate`.

Résultats finaux : **46 tests réussis sur PostgreSQL 17.11**, aucun test ignoré, avec Django **5.2.19**. Toutes les migrations sont appliquées ; `check` ne relève aucune anomalie ; `makemigrations --check --dry-run` ne détecte aucun changement ; le schéma OpenAPI est généré et validé sans erreur. La suite couvre connexions et CSRF, session fixation/logout, refus anonyme/inactif, périmètres de listes/comptes/détails/notes, substitution d'UUID dans la même organisation et entre organisations, flags/groupes Django ignorés, escalade par payload ou délégation, expiration/révocation en session existante, audit filtré/immuable/atomique, seed et budget de connexion concurrent. Les tests PostgreSQL ne sont pas substitués par SQLite. La sortie finale locale est conservée dans `.local/phase1-tests.log` (ignorée).

Deux erreurs spécifiques PostgreSQL ont été détectées puis corrigées pendant le développement : variable PL/pgSQL ambiguë dans le contrôle de sous-type et combinaison DISTINCT/FOR UPDATE dans la mutation CRM. Les régressions correspondantes passent dans la suite finale.

## Limites et suite

La matrice de rôles métier, les politiques de conservation et la procédure de provisioning de production restent à approuver. SSO, MFA, réinitialisation de mot de passe, interface d'administration des rôles et consultation applicative des audits globaux ne sont pas livrés. Les événements d'authentification globaux sont conservés en base et exclus des lecteurs d'audit limités à une organisation.

Le cluster local accorde CREATEDB au compte de développement pour les tests ; la production doit séparer propriétaire/migrations et rôle d'exécution sans DDL/TRUNCATE. Les triggers ne protègent pas contre un DBA privilégié. Les buckets expirés nécessitent une purge opérationnelle selon la rétention validée. TLS/proxy, sauvegardes/restauration, charge et revue de déploiement restent la phase préproduction.

Docker/Compose et la CI hébergée n'ont pas été exécutés durant cette phase. La CI a été mise à jour pour exécuter `core identity` sur PostgreSQL. Aucun écran métier frontend, import, rapprochement actif ou intégration Carthago n'a été démarré.
