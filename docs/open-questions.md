# Questions ouvertes et décisions provisoires

## Inscription — décision du 22 novembre 2026

- Décision utilisateur : demande de compte, puis accord du responsable avant activation.
- La demande exige un code d'institution communiqué en interne ; aucun annuaire public.
  L'approbation utilise `users.manage` au périmètre organisation, sans rôle automatique.
- Pour la démonstration synthétique, `synthetic.supervisor.a` dispose d'un rôle
  démonstratif regroupant les capacités AICED disponibles, limité à SYNTHETIC-A.
  Ce rôle n'est pas un modèle de production ni une approbation des droits réels.
- L'email n'est pas vérifié ni notifié automatiquement. Le responsable doit vérifier
  l'identité par un canal interne. Définir une politique de rétention et de nouvelle
  demande après refus avant déploiement réel.
- Les anciennes procédures de transfert S5 ne couvrent pas la nouvelle table de
  demandes : aucune bascule/rollback historique ne doit être exécutée avec des
  demandes réelles sans étendre et valider leur inventaire.

## Démonstration synthétique — liaison des imports

- Décision utilisateur : pour les imports synthétiques de personnes et de sociétés,
  après revue et publication, créer un client AICED si son identifiant source est
  nouveau ; sinon actualiser uniquement les données source en lecture seule.
  Les données CRM éditables restent distinctes. Cette décision ne s'applique pas
  aux données opérationnelles et ne constitue pas une approbation Carthago.
- Pour cette démonstration uniquement, la colonne B identifie la personne ou la
  société dans l'organisation et le type de fichier ; les espaces de noms des
  personnes physiques et morales sont distincts. Un client existant créé à la
  main n'est jamais lié sur la seule base de son nom. Pour les données réelles,
  la portée d'unicité et les règles de conflit restent à approuver.
- Décision utilisateur pour la démonstration : D « Détenteur du compte » est
  l'identifiant du client ; E « Numéro de compte » est l'identifiant unique du
  compte. AH reste non interprétée. D doit correspondre exactement à une seule
  personne ou société synthétique de la même organisation ; si aucune ou plusieurs
  correspondent, la page attend une revue. Les changements de détenteur ne sont
  pas appliqués automatiquement.
- L'import reste possédé par Integration et les clients par Client & CRM. Dans la
  base locale explicitement marquée synthétique, le traitement Client découvre les
  lots publiés, persiste sa progression et réessaie les pages interrompues. Ce
  mécanisme ne constitue pas une autorisation pour les données opérationnelles.

## Réutilisation des règles de publication

- AMEN INVEST doit confirmer les politiques opérationnelles de chaque source,
  colonne clé et format ; une règle synthétique ne vaut jamais cette approbation.
- Les historiques non classifiés ne sont pas automatiquement requalifiés.
  Définir les approbations réelles et leur remplacement explicite avant usage
  opérationnel. Une éventuelle suppression du workflow API historique nécessite
  une décision de compatibilité distincte ; aucun historique ne doit être effacé.
- Les décisions MAP/OWN/VIS/LIFE de Client 360 restent requises. La réutilisation
  d'une approbation de snapshots ne les résout pas. Voir
  [le workflow](publication-rule-reuse.md).

## S17 — pilotage CRM dans les périmètres existants

- La demande autorise un reporting descriptif sur les données CRM vérifiées,
  sans nouveau droit d'équipe ou global. Confirmer la matrice direction/équipe,
  l'attribution des activités et la visibilité collective des agendas/brouillons
  avant toute extension de portée ; le libellé Pilotage CRM ne donne aucun droit.
- Confirmer le dictionnaire opérationnel et Africa/Tunis configurable ;
  complétude technique provisoire sans KYC, interactions déclarées sans preuve
  de contact, rendez-vous personnels et brouillons du créateur seulement.
- Les KPI financiers, valorisations, rétention et projections Carthago restent
  exclus. Les approbations MAP/OWN/VIS/LIFE sont toujours absentes.
- S16.1 est accepté comme observabilité livrée, mais son défaut intermittent
  HTTP 503 reste un risque de release non corrigé et instrumenté.

## S12 — agenda personnel provisoire

- Le périmètre S12 autorise explicitement la création/lecture/édition personnelles,
  sous les droits existants clients/interactions de l'organisation. Le créateur
  est fixé par la session ; aucun droit de lecture des agendas de collègues.
- Confirmer avec AMEN INVEST les participants, délégations, visibilité collective,
  annulation/archivage, activité réalisée et éventuel lien dossier. Aucune de ces
  fonctions n'est activée et aucune interaction réalisée n'est créée automatiquement.
- Confirmer si un chevauchement personnel doit avertir ou bloquer ; S12 permet les
  chevauchements et le signale explicitement. Les rendez-vous sur plusieurs jours
  et la récurrence ne sont pas implémentés.
- Valider formellement Africa/Tunis. `AICED_AGENDA_TIME_ZONE` accepte une zone IANA
  dans les fichiers d'environnement privés ; tout changement nécessite une revue
  de l'affichage des instants déjà stockés, des heures ambiguës et de la portée
  de l'édition sur une même journée. Aucun changement automatique du fuseau.
- Canaux, consentements, destinataires et politique de rappels/synchronisation
  restent à approuver ; aucune livraison email ou notification n'existe dans S12.

## S8 — décisions de recette métier

- Confirmer la priorité proposée : historique transversal livré en premier, puis
  worklist des prochaines actions déjà saisies, filtres CRM, pipeline et agenda.
  Les trois modules métier restent Panorama Clients, Pilotage Commercial et
  Pilotage Managérial ; Data Integration est transversal.
- Définir les résultats d'interaction et la notion de contact effectif : auteur
  d'une saisie, responsable commercial, échange enregistré et contact réel ne
  sont pas interchangeables. Aucun résultat/score n'est déduit des notes.
- Valider catalogue produits/offres, affectation et conversion d'opportunités,
  matrice DED/DG, sources/périodes/attribution et formules de chaque KPI avant
  leur calcul. La recette synthétique ne vaut pas accord métier ou production.
- Voir [le backlog avec critères d'acceptation](mvp-backlog.md) pour les
  dépendances, efforts indicatifs et éléments implémentables sans Carthago.

## Après S7 — prochaines tranches fonctionnelles

- Agenda : confirmer les participants, périmètres de visibilité, états de rendez-vous,
  rappels, canaux autorisés et règles de modification avant automatisation.
- Campagnes : confirmer ciblage, autorité de lancement, consentements, canaux,
  suivi et règles d'arrêt ; aucune règle de conversion ou KPI n'est déduite.
- Ces décisions complètent l'[analyse des écarts](functional-gap-analysis.md).

## Migration vers des services indépendants — audit

- Décision confirmée par l'utilisateur : cible service-based, déploiements et données propriétaires derrière Gateway ; préserver les fonctionnalités/migrations. La cible monolithique précédente est remplacée. Aucune extraction autorisée dans l'intervention d'analyse présente.
- Recommandation technique : conserver DRF, extraire Integration en premier après contrats Gateway/IAM/audit, puis IAM, Commercial et résidu Client. Les sept frontières, étapes, rollback et risques sont dans `migration/`.
- Avant bascule : valider le protocole de révocation inter-services équivalent au verrou actuel, la visibilité/latence de l'audit central, le responsable backup/restore, la fenêtre de maintenance, RPO/RTO et l'outil de retour après nouveaux commits. Aucun de ces points n'autorise à affaiblir les permissions ni à migrer de la production maintenant.

## Clarification utilisateur — 14 novembre 2026

- Aucune politique de propriété/mapping Carthago approuvée : écritures et rapprochements des identités, comptes et finances source bloqués ; cette restriction ne bloque pas le CRM AICED autonome.
- Première tranche commerciale historique : prospects, interactions et opportunités. S12 ajoute l'agenda personnel ; S14 ajoute les brouillons privés de campagnes. Ciblage, activation, communications, agenda collectif et pilotage managérial restent à cadrer/développer.
- Les statuts de prospect sont des qualifications manuelles, sans score ni transition automatique. La définition de conversion, les indicateurs managériaux, les règles de qualification et l'affectation/réaffectation commerciale restent à valider avant automatisation.

## Décision utilisateur du 19 novembre 2026

- Pour le classeur des personnes physiques, utiliser la colonne B comme identifiant pour la règle d'import. Cette décision ne précise pas le sens de la colonne AC, la portée d'unicité entre sources, ni les liens avec les clients AICED ou les comptes. Elle n'approuve pas automatiquement une règle opérationnelle ni les lots existants.

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
- `Tier Personnes Physiques.xlsx`, feuille `Tier`, contient deux en-têtes `Identifiant` (B et AC). B est choisi pour la règle d'import ; le sens de AC et la portée d'unicité restent à confirmer. Pas de dictionnaire basé uniquement sur le libellé.
- Les premières colonnes des trois classeurs sont sans libellé. Les ignorer uniquement après validation du modèle d'import.
- La feuille des personnes morales comporte des champs Sexe, Civilité, Etat Civil et Pays de naissance. Ne pas appliquer les règles des personnes physiques automatiquement.
- Confirmer la relation entre Identifiant du compte et tiers ; le détenteur et le nom ne prouvent pas une identité.
- Confirmer la portée des exports (complet/partiel), leur date d'effet, les dates Excel, les formats d'identifiants et les valeurs manquantes.
- Définir double contrôle et interdiction d'auto-approbation pour les lots et décisions d'identité.

## S10 — nomenclature CRM

- AMEN INVEST souhaite-t-il une nomenclature de professions/secteurs, des alias
  ou des règles de normalisation ? Qui approuve et maintient ces valeurs ?
  S10 conserve les libellés bruts déclarés et leurs variantes ; aucun rapprochement
  Carthago ni nettoyage automatique n'est effectué.

## Historique de l'environnement initial

Ce constat est historique ; les outils Docker sont désormais disponibles et
les résultats actuels figurent dans les recettes S7–S14.
Le dépôt initial contient uniquement des répertoires vides et neuf documents de référence. Node, npm, Docker et Git ne sont pas disponibles dans le PATH lors de l'inspection. Les vérifications impossibles seront signalées explicitement.

## S14 — campagnes manuelles

- Le brouillon privé au créateur est une restriction provisoire de préparation,
  sans responsable métier ni transfert. Approuver propriété, partage,
  affectation et matrice campagnes ; S14 réutilise opportunities.view/manage
  sans attribuer de grant automatiquement.
- Approuver statuts/transitions, validation, activation/annulation, rétention,
  critères, cibles clients/prospects, consentement/exclusions. Les notes S14
  ne sont ni des segments ni des requêtes exécutées.
- Approuver canaux, destinataires, contenus, rappels et attribution/KPI avant
  toute communication ou mesure. Aucun email ou lancement implémenté.
- Confirmer Africa/Tunis ; AICED_COMMERCIAL_TIME_ZONE est configurable et les
  dates prévues sont civiles.
# S15 — décisions supplémentaires à confirmer

- Valider les champs et l'applicabilité physique/morale d'une complétude métier.
  L'indicateur livré est une présence technique CRM provisoire, jamais KYC.
- Approuver nomenclatures et traitement des variantes ; aucune fusion réalisée.
- Fournir autorité/mappings validés pour naissance, revenus, risque et produits.
- Cadrer MAN-01 : mesures descriptives, périodes et matrice de visibilité direction.

## S16 / préparation S17

- S16 préparation source (demande ultérieure distincte du reporting) : décisions
  MAP-01/02/03, OWN-01, VIS-01/02, LIFE-01 dans
  [la matrice d'approbation](source-mapping-approval-matrix.md). Fournir les
  approbateurs, versions et périmètres avant tout affichage réel dans Client 360.
  Le compte peut-il avoir plusieurs titulaires ? Quelle autorité pour le lien
  source/UUID AICED et quelle procédure de correction/révocation ? Le modèle
  FinancialAccount actuel possède un seul Party obligatoire : aucune adéquation
  métier n'est supposée et aucune restructuration n'est faite en préparation.

- Investigation imports/accueil du 2026-11-16 : les colonnes source sont
  inventoriées dans [import-source-mapping.md](import-source-mapping.md).
  Confirmer B ou AC pour les personnes physiques et les relations avec
  Détenteur du compte / Identifiant du compte titre. Aucun de ces champs
  n'est assimilé à un UUID AICED. Valider la visibilité source par objet et
  l'autorité par champ avant toute projection dans Client 360.
  Risque LAB/FT ne signifie pas risque d'investissement. Les règles
  synthétiques approuvées en recette ne sont pas des approbations métier.

- Les compteurs opérationnels S16 décrivent les dossiers visibles, pas la
  performance ou une activité attribuée à un responsable. Valider toute
  attribution auteur/responsable et les éventuels résultats commerciaux.
- Approuver la matrice direction/équipe et la visibilité par mesure avant S17.
  Aucun droit global, accès financier ou agenda d'autrui n'est attribué en S16.
- Confirmer le fuseau configurable Africa/Tunis et les périodes/mesures attendues.
- Une évolution historique des statuts/campagnes nécessiterait un dictionnaire
  d'événements approuvé ; `updated_at` ne prouve ni un changement précis ni un envoi.
- Confirmer le traitement des prospects clos dans les relances : S16 conserve
  les mêmes compteurs tous statuts que la worklist existante et l'indique à l'écran.
