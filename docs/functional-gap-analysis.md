# AICED — analyse des écarts fonctionnels après S7

Base de revue : code des routes/écrans, `client-360-data-management-status.md`,
`prospects-mvp-status.md`, `import-templates.md` et `open-questions.md`.
Cette analyse distingue le socle livré des fonctions restantes ; elle ne vaut
pas recette métier ni implémentation de ces fonctions. Les quatre services
restent la cible, sans nouvelle extraction architecturale.

| Module métier | Socle existant soumis à la recette Docker | Écarts à traiter |
|---|---|---|
| Client & CRM | Panorama, recherche/pagination, Client 360, identité AICED, profil CRM, lecture financière autorisée, interactions, contrôle de version | Pièces jointes et rétention, affectation/réaffectation, rapprochement explicite et vue portefeuille complète ; segmentation/indicateurs bloqués sans définitions approuvées |
| Commercial | Prospects physiques/moraux, qualification manuelle, prochaine action/date, interactions et opportunités, estimations Decimal et concurrence optimiste | Agenda/rendez-vous et rappels, campagnes, pilotage managérial ; conversion et automatisations exigent des règles métier validées |
| Data Integration | Dépôt XLSX, staging/validation, rejets CSV, politiques à double contrôle, publication de snapshots immuables et idempotence | Mapping/propriété source approuvés, rapprochement revu, connecteur Carthago en lecture seule après contrat technique fourni, exploitation/purge et contrôle antivirus |

Ordre de travail déjà retenu : terminer la tranche CRM autonome, puis agenda,
campagnes et pilotage. Chaque tranche doit préciser les actions autorisées et
leurs périmètres, les états métier, l'audit transactionnel et les scénarios de
recette avant ses endpoints. Inspecter visuellement les maquettes concernées
avant de reproduire leurs écrans. Les fonctions bloquées par une décision
métier ne doivent pas être remplacées par des valeurs ou des règles inventées.

Les décisions encore nécessaires sont consignées dans `open-questions.md` :
matrice de production, définition des conversions et KPI, règles de campagne et
de rappel, propriété des champs, identifiants source et liens compte/tiers,
rétention et autorité d'approbation. Le CRM autonome peut progresser sans accès
Carthago ; aucune publication source vers les clients/comptes n'est autorisée
par les tests de snapshots synthétiques.
