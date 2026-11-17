# Bilan phase 0

## Objectif et périmètre
Analyser les sources disponibles, proposer l'architecture et livrer un socle de développement. Les modules métier ne sont pas implémentés.

## Fichiers livrés
- `docs/` : architecture, relations, permissions, ingestion/rapprochement, stratégie UI, backlog/acceptation, questions ouvertes, analyse des références et ce bilan.
- `AGENTS.md`, `.gitignore`, `.env.legacy.example`, `README.md`, `compose.legacy.yaml`, `infra/README.md` : conventions et environnement local.
- `backend/config`, `identity`, `core`, `ingestion`, requirements et Dockerfile : configuration Django/DRF, User UUID et migration, refus par défaut, vie API, session courante protégée, schéma OpenAPI protégé, logs JSON minimaux et adaptateurs explicitement inactifs.
- `frontend/` : Vite/React/TypeScript/Tailwind, Router et Query, validation Zod de la réponse de vie et écran technique en français. RHF/Recharts déclarés pour les phases suivantes, sans formulaire ni graphe artificiel.
- `scripts/inspect_references.py` : outil local de revue des PDF et structures Excel ; ses sorties privées sont ignorées.

## Vérifications réellement exécutées
- Extraction locale des six PDF et inspection des feuilles/en-têtes/types/formats échantillonnés des trois classeurs.
- Inspection visuelle des pages rendues mentionnées dans `reference-analysis.md`.
- Django `check` : aucune anomalie.
- Migration User générée ; `makemigrations --check --dry-run` avec configuration de test : aucun changement.
- Cinq tests `core` passés avec base SQLite éphémère ; migrations auth/identity/session appliquées dans cette base.
- `spectacular --validate` : schéma OpenAPI généré et validé, stocké localement hors versionnement.
- Installation frontend avec runtime Node portable local ; `tsc --noEmit && vite build` réussi (182 modules). Deux avertissements de commentaires d'annotation dans Zod ont été émis, sans erreur de compilation. Verrou npm généré.
- Dépendances Python runtime fixées dans `backend/requirements.lock`. Dockerfiles utilisent les verrous ; CI PostgreSQL et frontend configurée dans `.github/workflows/ci.yml`, mais pas exécutée sur une plateforme CI durant cette session.
- La première invocation sans label depuis la racine n'a découvert aucun test ; elle a été corrigée et les cinq tests ont ensuite été exécutés avec le label explicite `core`.

## Limites
PostgreSQL, images Docker, démarrage Compose et parcours navigateur non vérifiés : Docker absent. Node/npm absents au départ ; le build frontend a été vérifié avec un runtime portable téléchargé dans `.tools/`, ignoré. La génération initiale de migration a averti que l'hôte PostgreSQL `db` n'était pas joignable depuis l'hôte ; la cohérence et l'application ont été contrôlées avec SQLite, pas avec PostgreSQL. Les dépendances et images nécessitent une revue de vulnérabilités avant préproduction.

Pas d'authentification interactive, RBAC métier, périmètres objet/organisation, audit de sécurité durable ou endpoints CRM au socle ; ces fondations constituent la phase 1 et doivent précéder les données client. Aucun succès d'import, résultat IA, métrique financière ou fidélité aux 16 maquettes manquantes n'est revendiqué.
