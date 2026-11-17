# S8 — backlog MVP fonctionnel

Gestion des publications : réutilisation d'une approbation par source/schéma/
format/usage, suggestion après validation, historique séparé, dédoublonnage des
propositions identiques et remplacement explicitement approuvé. Chaque lot
conserve sa revue indépendante. Voir [le workflow et la recette](publication-rule-reuse.md).
Les anciennes règles non classifiées ne constituent aucune approbation métier
opérationnelle. Prochaine décision AMEN INVEST : politiques réelles et matrice
MAP/OWN/VIS/LIFE ; aucun rapprochement client/compte activé. Risque 503 inchangé.

S17 — Pilotage CRM : vue descriptive `/pilotage-crm`, portefeuille et complétude
technique, activités par période, relances, opportunités et brouillons, dans
les seules autorisations existantes. Aucun accès d'équipe implicite ; agendas
et brouillons personnels. [Définitions et recette S17](migration/s17-managerial-crm-reporting.md).
Prochaine décision : matrice managériale/attribution et éventuelle visibilité
collective, avant toute extension de portée. Les mappings Carthago restent bloqués.

S16.1 — diagnostic pipeline : trois suites Docker complètes passent, mais le
503 historique n'est pas reproduit ni expliqué. **Incrément de diagnostic et
d'observabilité accepté comme terminé ; défaut et risque de release ouverts**,
sans changement de budget ni d'autorisation. Voir [l'enquête S16.1](s16-1-pipeline-regression.md).
Les incréments fonctionnels non bloqués sont autorisés ; capturer la prochaine
occurrence avant toute correction causale du pipeline.

S16 préparation source / Client 360 : matrice d'approbation, contrat signé
de démonstration et aperçu synthétique de six cas livrés ; aucune identité,
relation de compte ou donnée réelle activée. Le précédent S16 reporting reste
un jalon historique distinct. Voir [la matrice](source-mapping-approval-matrix.md),
[le contrat](source-mapping-contract.md) et
[la recette](source-mapping-preparation-validation.md).
Prochaine étape DATA-01 : faire approuver MAP-01/02/03, OWN-01, VIS-01/02 et
LIFE-01, puis spécifier une lecture source limitée aux champs et dossiers
explicitement autorisés. Aucun registre de liens ou changement de propriétaire
de base n'est décidé ici. Les extensions collectives de S17 restent conditionnées
à leur matrice ; le MVP dans les droits existants est décrit en tête du backlog.
Historique de recette S16 : les parcours source passaient, mais deux suites
complètes avaient un échec 503 du pipeline S13, malgré un repassage isolé réussi.
Le risque intermittent reste ouvert en S16.1 même si une suite ultérieure passe ;
ne pas relever les limites ni affaiblir l'autorisation.

Correction imports/accueil (2026-11-16) : connexion de l'accueil aux API CRM
existantes, explication des blocages de publication et historique visible.
[Mappings source proposés](import-source-mapping.md), sans fusion ni KPI financier.
Étape préalable à toute consommation source dans Client 360 : approbation
AMEN INVEST des clés physiques B/AC, liens titulaire/compte/tiers, propriété
par champ et politique de visibilité objet ; ensuite seulement définir un
contrat de lecture source signé et borné. Ce contrat n'est pas livré ici.
La visibilité collective au-delà du MVP S17 reste conditionnée à la matrice approuvée.

S16 ajoute le rapport opérationnel `/activite-commerciale` : agrégats CRM
autorisés, périodes/type/jours et stocks explicitement séparés. Définitions,
limites et recette : [S16](migration/s16-commercial-activity.md).
Recommandation historique S16 : **S17 — tableau de bord CRM managérial**, désormais
livré dans les seuls périmètres existants ; matrice direction/attribution à approuver
pour toute extension collective.
Les objectifs et KPI financiers restent exclus.

S15 regroupe la segmentation avancée disponible et la qualité technique CRM :
type physique/moral, profession/secteur, présence de champs, intervalle de
complétude, résumés autorisés et fiche 360. Définition technique provisoire,
sans migration ni correction source. Voir [la recette S15](migration/s15-segmentation-quality.md).
La priorité suivante est MAN-01 : cadrer puis livrer les rapports d'activité
commerciale et tableaux CRM managériaux avec permissions et mesures approuvées.
Les anciennes recommandations de ciblage ci-dessous restent historiques.

## Priorité après S15 — MAN-01 / activité commerciale CRM

1. Faire approuver le dictionnaire descriptif (événements pris en compte,
   date de référence, périodes Africa/Tunis, auteur vs responsable) et la
   matrice de visibilité direction. Sans cette matrice, aucun accès global.
2. Livrer un premier rapport d'activité sur les données CRM disponibles,
   puis les vues managériales correspondantes, dans les propriétaires existants.
   Aucun revenu ou conversion automatique dérivé des statuts manuels.
3. Recette : population autorisée avant agrégats, bornes de période et jeux
   synthétiques de référence approuvés, révocation et erreurs fermées, navigation
   vers les dossiers autorisés, tests navigateur/Nginx/Docker et contrats.

Blocages indépendants : données source et formules des KPI financiers MAN-02,
taxonomies et complétude métier S15, règles de ciblage/activation COM-07.

Priorités proposées à partir de `AICED.pdf` p.6–8 et du cahier §§5–7. Efforts
indicatifs développement + tests, hors attente métier : S = 1–2 jours, M = 3–5,
L = 6–10, XL = plusieurs incréments. Ce ne sont pas des engagements calendaires.
Valeur et dépendances priment sur l'ordre des maquettes. Pas de nouvelle
extraction ni de restructuration des propriétaires.

## Incréments réalisables ou préparables

| ID / priorité | Valeur et périmètre | Dépendances / effort | Critères d'acceptation |
|---|---|---|---|
| COM-01 / P0, premier S8 | Historique transversal : retrouver un échange sans parcourir chaque dossier | `clients.view` ∩ `interactions.view`, scope prospect, modèle Interaction Client existants ; S | Création réelle depuis fiche, recherche après rechargement, retour à la fiche ; recherche client/objet/notes, type, dates inclusives Tunis, pagination stable/bornée ; scoping avant compteur et filtres, refus IT/anonyme/révocation ; état vide/erreur et mobile ; aucune finance/résultat déduit ; 38 routes/schémas historiques inchangés, extension additive documentée |
| COM-02 / P0, livré S9 | Worklist des prochaines actions de prospects | Prospect et permissions existants ; S | Échéances Tunis, recherche/statut/dates/tri/pagination, scoping avant compteurs ; lien fiche et qualification existante ; sans score, clôture ou rappel automatique ; validation dans migration/s9-prospect-followups.md |
| PAN-01 / P1, livré S10 | Recherche profession/secteur CRM | CRMProfile existant ; S | Filtres exacts/presence, recherche/type/tri/page après scoping ; options et effectifs visibles uniquement, absence distincte, variantes conservées ; aucune inférence VIP/risque ; recette migration/s10-client-segmentation.md |
| PAN-05 / P1, S15 | Segmentation descriptive étendue et qualité technique CRM | Champs existants ; définition technique provisoire, sans migration | Type visible dynamique, filtres combinés d'intervalle/absences, résumé autorisé avant pagination, fiche 360 et source en lecture seule ; aucune normalisation ni score KYC ; tests de calcul/isolement/révocation et recette Docker dans migration/s15-segmentation-quality.md |
| COM-03 / P1, livré S11, capacité S13 | Pipeline transversal des statuts existants | Commercial propriétaire, autorisation objet Client HTTP signée, contrat compact borné ; M | Kanban/recherche/tri/lien précis, Decimal/version, périmètre avant compteurs/pages ; pannes/révocations fermées, conflits 409 et audit/outbox ; plafond global S11 remplacé par un parcours à mémoire bornée et budget 4 s, vérifié à 10 000 opportunités synthétiques ; recettes migration/s11-opportunity-pipeline.md et migration/s13-pipeline-scalability.md |
| COM-04 / P1, MVP personnel livré S12 | Agenda personnel : création, lecture, édition, calendrier mensuel et liste chronologique | Client & CRM ; droits clients/interactions existants ; owner-only provisoire autorisé en S12 | Date/heures Tunis configurables, version/409/audit/outbox, propriétaire immuable, isolation avant compteurs/calendrier/pages ; chevauchements autorisés provisoirement, annulation/participants/équipe/notifications désactivés ; recette migration/s12-manual-agenda.md |
| PAN-02 / P2 | Dossier documentaire CRM | Classification/rétention/stockage approuvés ; L | Autorisation objet sur dépôt/liste/téléchargement, stockage privé, quotas/contenu, fichiers synthétiques, audit et suppression revue ; aucune finance implicite pour IT |
| COM-05 / P2, brouillons S14 | Préparation personnelle de campagnes manuelles | Commercial, permissions existantes provisoires ; ciblage/états/responsable à confirmer | Nom/description/dates/notes préparatoires, privé au créateur, recherche/tri/page, version/409 et audit/outbox ; aucun client associé, segment exécuté, effectif de cible, lancement ou envoi ; recette migration/s14-manual-campaigns.md |
| COM-08 / P1, livré S16 | Rapport descriptif d'activité CRM | Données/permissions existantes, définitions opérationnelles documentées | Période/type/jour bornés, compteurs cohérents avec sources autorisées, stocks séparés, erreurs/révocations/pannes fermées ; recette migration/s16-commercial-activity.md |
| MAN-01 / P1, MVP S17 | Pilotage CRM dans les périmètres existants | Données et règles S15/S16 réutilisées ; extensions direction/équipe et attribution toujours à approuver | Portefeuille/complétude courants, interactions/rendez-vous par période et type, relances/statuts/brouillons, graphiques/tables accessibles ; portée avant agrégats, agendas/brouillons personnels, révocation/pannes fermées ; aucune finance ou rétention ; recette migration/s17-managerial-crm-reporting.md |

COM-01 précède l'agenda : demande explicite des spécifications, forte valeur
quotidienne, données/permissions présentes, faible coût, aucune règle nouvelle
de rendez-vous/rappel/campagne. Il ajoute une lecture et un écran, sans table ni
mutation ; créations/éditions réutilisent les services transactionnels existants.
Il ne termine pas le module Commercial.

## Incréments bloqués ou conditionnels

| ID / priorité métier | Travail | Approbation/donnée nécessaire, effort | Recette après levée du blocage |
|---|---|---|---|
| DATA-01 / P0 pour finance réelle | Mapping/rapprochement source transversal | Identifiants B/AC, lien tiers/compte, propriété champ par champ, accès Carthago read-only ; L–XL | Staging/revue/provenance, conflits explicites, publication idempotente vers le propriétaire via contrat approuvé ; jamais fusion par nom, suppression par absence ou écrit Carthago |
| PAN-03 / P1 | Fiche financière/portefeuille/risque/segments source | DATA-01, positions/valorisation et autorité données sensibles ; L–XL | Provenance/date de situation, manquants explicites, finance scoppée, CRM/source séparés ; démonstration synthétique marquée seulement |
| COM-06 / P1 | Produits, affectations et conversion | Catalogue, auteur vs responsable, conversion prospect/client et états approuvés ; M–L | Champs/transitions explicites, revalidation scope/version, audit atomique et tests révocation ; pas de déduction depuis notes/titre |
| COM-07 / P1 | Notifications et lancement de campagnes | Destinataires, consentement, canaux, rappels/annulation/déduplication, autorité lancement ; L | Transport synthétique sans envoi réel, reprise idempotente, permissions à l'action ; diffusion externe uniquement sur instruction explicite |
| MAN-02 / P0 du module | OPCVM, ouvertures/conversions, encours, courtage/frais/rotation, tendances/exports | DATA-01, mouvements/valorisation, KPI/périodes/attribution et matrice DED/DG ; XL | Valeurs de référence approuvées synthétiques, calculs exacts/justifiables, filtres avant agrégats/export, périodes/annulations cohérentes, isolation ; pas de données réelles simulées |
| PAN-04 / P2 | Scoring/engagement/rétention | Formules, seuils, données et usage AMEN INVEST ; L–XL | Jeux de référence et méthode/version visibles, valeurs absentes distinctes de zéro, aucune décision automatique non approuvée |
| MAN-03 / P2 | Satisfaction/conformité/CEA | Questionnaires/sources, ratios et autorité conformité ; L | Traçabilité et habilitations propres ; aucun score LAB ou conformité déduit d'une maquette |

AMEN INVEST valide priorités finales, rôles métier, règles ambiguës et recette.
COM-01/02 et PAN-01 peuvent avancer sur données CRM autorisées ; les contrats et
tests des autres incréments peuvent être préparés. Matrice production, recette
visuelle et gouvernance restent distinctes des tests Docker. IA/prédictions/
recommandations restent conditionnées au fournisseur, à la rétention et aux
périmètres de recherche approuvés.

S9 : COM-02 livré dans le périmètre prospect existant ; validation et limites dans
[migration/s9-prospect-followups.md](migration/s9-prospect-followups.md).
S10 : PAN-01 livré. S11 : COM-03 livré sur les statuts existants, sans probabilité
ou revenu déduit. Prochain incrément proposé : COM-04, agenda manuel après
validation AMEN INVEST des participants, visibilité, fuseau et annulation.

S12 : MVP personnel COM-04 livré dans la portée explicitement autorisée ; extension
collective/annulation encore bloquée par les décisions métier. Prochain incrément
technique alors recommandé : [remédiation bornée de la limite S11](s11-pipeline-limit-remediation.md).
S13 réalise cette remédiation dans les quatre services existants ; mesures,
tests et limites dans [la recette S13](migration/s13-pipeline-scalability.md).
Retour au backlog fonctionnel : **COM-05, campagnes manuelles**, candidat au
prochain incrément après cadrage AMEN INVEST des états, du responsable et du
ciblage. Aucun lancement, envoi, score ni résultat financier implicite.

S14 livre uniquement les **brouillons personnels COM-05**, sans ciblage exécuté
ni association client. La sélection explicite de dossiers de l'ancien backlog
reste conditionnelle : matrice campagnes, ownership/affectation et règles de
cible à approuver par AMEN INVEST. Prochain incrément : cadrage puis sélection
manuelle autorisée par Client, sans diffusion.
[Recette S14](migration/s14-manual-campaigns.md).


Import review correction increment: see [workflow and verification](import-workflow-corrections.md) and [approval-only proposals](import-publication-approval-proposals.md). This improves reviewer navigation and truthful publication blockers; it does not approve operational source rules or activate Client 360 mappings. S16.1 intermittent pipeline HTTP 503 remains an open release risk.
