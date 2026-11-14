# Phase frontend — trois écrans

Implémentation : Connexion, Tableau de bord, Panorama Clients en React/TypeScript/Tailwind. Layout, jetons CSS, composants et contrats OpenAPI partagés. Navigation, login/logout réel, recherche et pagination serveur, fiche minimale, chargement/erreur/vide et refus d'accès. Seules données synthétiques utilisées pour la vérification.

## Revue et corrections confirmées

- Élevé : suppression du cache d'identité à la déconnexion laissant l'observer sur une ancienne identité. Correction : conserver ce cache, annuler les requêtes et y écrire null après succès serveur ; supprimer les caches privés. Régression navigateur login → clients → logout.
- Moyen : redirection de connexion pouvant écraser la destination protégée initiale. Destination locale validée partagée entre redirection déclarative et navigation après soumission ; régression `/clients` anonyme → connexion → clients.
- Périmètre serveur : recherche et pagination appliquées après queryset autorisé ; test du nom et UUID d'un client interdit, du type invalide et de chaque page bornée à l'organisation.
- Visuel : couleurs, sélection arrondie de sidebar, artwork CSS Connexion, tailles, espacement et labels de graphiques corrigés après comparaison avec les pages PDF rendues.

## Vérification

- `python scripts/backend_check.py test identity clients audit ingestion core --noinput` : **65 tests PostgreSQL réussis**, incluant isolation inter-client, inter-organisation, finance et escalade de privilèges. La commande sans labels depuis la racine découvre zéro test : ne pas l'utiliser comme preuve.
- `python scripts/backend_check.py migrate --noinput` : aucune migration restante.
- `python scripts/backend_check.py makemigrations --check --dry-run` : aucun changement de modèle sans migration.
- Build TypeScript/Vite : réussi. Avertissements non bloquants de Rollup sur deux annotations de commentaires dans Zod ; aucune erreur TypeScript.
- `npm audit --omit=dev --json` : zéro vulnérabilité connue signalée pour les dépendances production lors de cette vérification ; ce résultat ne constitue pas un audit exhaustif du code ou de l'infrastructure.
- Chromium développement : **6 scénarios réussis** : connexion/validation/destination initiale/déconnexion ; refus IT/finance ; chargement/503/retry ; révocation/expiration ; contrat comptes/type/pagination ; captures et navigation responsive (y compris Connexion mobile). Commande : `python scripts/frontend_e2e.py --grep 'real session|IT cannot|client loading|revoked permissions|server pagination|reference screenshots'`.
- Chromium sur build production : **1 scénario réussi** : `python scripts/frontend_e2e.py --production --grep 'production build'` confirme que `?apercu=maquette` n'active aucun exemple fictif pour un manager habilité. Rapport séparé `.local/browser-production-report.json`.
- Le runner utilise les comptes seed synthétiques, lance puis arrête Django/Vite sur des ports temporaires, relève seulement pour son serveur les budgets de tentatives répétées. Les tests de sécurité backend conservent les seuils ordinaires. Secrets locaux jamais imprimés. Le scénario production est ignoré lors d'une exécution complète en développement ; ce n'est pas une couverture production implicite.
- Captures privées : `.local/ui-review/screens/` ; rapport navigateur `.local/browser-report.json`. Aucune trace contenant les requêtes de connexion n'est enregistrée.

## Limites et fonctions absentes

Pas de contrat backend pour les agrégats, encours, risques, segmentation, scoring, historique ou modules commerciaux : état indisponible explicite en mode API. Aperçu maquette développement seulement, étiqueté fictif, sans écritures et sans règles métier. Exports, création client, notifications, Client 360 complet, récupération automatique de mot de passe, SSO/MFA, 13 autres écrans et Carthago non implémentés.

Comparaison visuelle humaine, aucune identité pixel certifiée. Inter est une approximation de police ; tracés Recharts approximatifs. Responsive adapté sans référence mobile. Les droits frontend peuvent rester visibles jusqu'à leur prochain rafraîchissement (30 secondes/focus/manuel), mais les accès serveur sont refusés immédiatement. Production, matrice métier, accessibilité complète et intégration de source exigent une recette distincte.
