# Conventions AICED

- React/TypeScript/Vite/Tailwind, Router, Query, RHF/Zod et Recharts ; Django/DRF/PostgreSQL. Monolithe modulaire, pas de microservices sans besoin démontré.
- Lire les documents `docs/` avant changement. Priorité : contraintes utilisateur > cahier des charges > AICED > maquettes > terminologie Carthago.
- Carthago strictement en lecture seule. Aucun endpoint, schéma ni credential inventé. CRM autonome.
- Autorisations serveur explicites, refus par défaut, périmètre organisation/objet appliqué à toute voie d'accès. IT ne reçoit pas implicitement les données financières.
- Identifiants internes indépendants des identifiants source. Finances source séparées du CRM éditable. Jamais de fusion incertaine ni suppression par absence d'export.
- Import via staging, validation, revue et publication transactionnelle idempotente ; conserver provenance et historique. Politique de propriété approuvée avant publication source.
- Ne pas committer références privées, extractions, données client, secrets ou uploads. Données de test synthétiques uniquement.
- Pas de règle de score, KPI ou identité inventée. Inscrire les inconnues dans `docs/open-questions.md`.
- Français visible dans l'interface. Reproduire les maquettes seulement après inspection visuelle ; ne pas prétendre une fidélité non vérifiée.
- Logique métier dans services backend ; React compose les écrans. Tests proportionnés, tests d'isolation obligatoires avant endpoints métier.
- Travailler par phases révisables. Rapporter les vérifications exécutées et limites ; aucune fonctionnalité déclarée opérationnelle sans test.
