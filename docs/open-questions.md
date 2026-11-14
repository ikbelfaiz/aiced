# Questions ouvertes et décisions provisoires

## Migration vers des services indépendants — audit

- Décision confirmée par l'utilisateur : cible service-based, déploiements et données propriétaires derrière Gateway ; préserver les fonctionnalités/migrations. La cible monolithique précédente est remplacée. Aucune extraction autorisée dans l'intervention d'analyse présente.
- Recommandation technique : conserver DRF, extraire Integration en premier après contrats Gateway/IAM/audit, puis IAM, Commercial et résidu Client. Les sept frontières, étapes, rollback et risques sont dans `migration/`.
- Avant bascule : valider le protocole de révocation inter-services équivalent au verrou actuel, la visibilité/latence de l'audit central, le responsable backup/restore, la fenêtre de maintenance, RPO/RTO et l'outil de retour après nouveaux commits. Aucun de ces points n'autorise à affaiblir les permissions ni à migrer de la production maintenant.

## Clarification utilisateur — 14 novembre 2026

- Aucune politique de propriété/mapping Carthago approuvée : écritures et rapprochements des identités, comptes et finances source bloqués ; cette restriction ne bloque pas le CRM AICED autonome.
- Première tranche commerciale : prospects, interactions et opportunités ; agenda, campagnes et pilotage managérial restent à développer.
- Les statuts de prospect sont des qualifications manuelles, sans score ni transition automatique. La définition de conversion, les indicateurs managériaux, les règles de qualification et l'affectation/réaffectation commerciale restent à valider avant automatisation.

## Bloquants de validation métier
- Client 360 / Data Management : staging et snapshots immuables disponibles ; confirmer le sens des deux Identifiant physiques, la relation compte/tiers et la propriété champ par champ avant toute publication vers les clients/comptes. Le choix ISO/DMY est désormais explicite et doit correspondre à une règle revue ; aucun ordre jour/mois n'est autodétecté. Les rôles operator/reviewer et les règles synthétiques de test ne constituent pas une approbation métier production.
- Résolu pour cette phase : les 16 maquettes sont dans `references/interface_aiced 2/`. Connexion, Tableau de bord et Panorama Clients ont été inspectés visuellement ; comparaison et limites dans `frontend-design-system.md`. Les 13 autres écrans restent à inspecter avant implémentation.
- Quel est le mode d'intégration Carthago autorisé ? Aucun accès technique, schéma physique ni contrat API n'est fourni. L'adaptateur automatique restera désactivé.
- Faire approuver la matrice rôles × actions × périmètres. Les intitulés de rôles ne valent pas habilitation.
  Phase 1 implémente le mécanisme avec des rôles synthétiques exclusivement. Les scopes `assigned` et `organization` et les règles conservatrices de délégation sont des choix techniques documentés, pas une matrice métier approuvée. Les définitions de rôles production et le bootstrap opérateur restent à valider.
- Définir l'autorité champ par champ, notamment les identités, adresses, risques LAB/FT et données financières. Publication financière bloquée sans politique approuvée.
- Définir les règles de segmentation, scoring, indicateurs, devises, valorisation, périodes et conversions. Pas de résultats calculés avant validation.
- Définir durée de conservation, suppression, chiffrement, résidence des données, sauvegardes et procédure d'incident avec les responsables habilités.
- Confirmer le mécanisme SSO, MFA, désactivation des comptes et politiques de session. Authentification Django locale pour le développement seulement.
  Connexion locale, CSRF, throttling partagé et révocation de périmètre sont implémentés en Phase 1. Validation des seuils, purge des buckets et consultation opérateur des audits globaux à organiser avant production.

## Questions issues des classeurs
- `Tier Personnes Physiques.xlsx`, feuille `Tier`, contient deux en-têtes `Identifiant` (B et AC). Sens et unicité à confirmer ; pas de dictionnaire basé uniquement sur le libellé.
- Les premières colonnes des trois classeurs sont sans libellé. Les ignorer uniquement après validation du modèle d'import.
- La feuille des personnes morales comporte des champs Sexe, Civilité, Etat Civil et Pays de naissance. Ne pas appliquer les règles des personnes physiques automatiquement.
- Confirmer la relation entre Identifiant du compte et tiers ; le détenteur et le nom ne prouvent pas une identité.
- Confirmer la portée des exports (complet/partiel), leur date d'effet, les dates Excel, les formats d'identifiants et les valeurs manquantes.
- Définir double contrôle et interdiction d'auto-approbation pour les lots et décisions d'identité.

## Environnement
Le dépôt initial contient uniquement des répertoires vides et neuf documents de référence. Node, npm, Docker et Git ne sont pas disponibles dans le PATH lors de l'inspection. Les vérifications impossibles seront signalées explicitement.
