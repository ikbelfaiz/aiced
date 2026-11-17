# S8 — validation des écarts fonctionnels AICED

Publication Excel : règles réutilisables et suggestion bornée par organisation,
type, schéma, format de dates et usage synthétique/opérationnel. Les historiques
et liens de publication sont conservés, sans approbation ni reclassification
automatique. [Détails et vérifications](publication-rule-reuse.md). L'approbation
des politiques opérationnelles et des relations source/Client 360 reste requise.

S17 : Pilotage CRM `/pilotage-crm`, données vérifiées dans les périmètres
existants : clients/types/complétude technique, interactions/rendez-vous par
période/type, relances, opportunités et brouillons personnels. Dictionnaire,
autorisations et recette dans [S17](migration/s17-managerial-crm-reporting.md).
Le reporting collectif direction/équipe, l'attribution, les KPI financiers et
la rétention restent non approuvés et non implémentés. Aucun mapping source activé.

S16.1 : trois suites navigateur Docker complètes réussies avec diagnostics,
sans reproduction du 503 historique. **Cause et correction non démontrées ;
validation de release S16 ouverte.** Le diagnostic/observabilité est accepté
comme terminé ; le risque 503 reste ouvert, indépendamment des incréments
fonctionnels autorisés. Voir [l'enquête](s16-1-pipeline-regression.md).
L'aperçu source reste exclusivement synthétique et ne confirme aucune identité.

S16 préparation source / Client 360 (désignation de la demande courante,
distincte du S16 reporting historique) : démonstration synthétique de six cas
de rapprochement, sans lecture d'import réel ni relation persistée. La fiche
conserve le blocage explicite des données source réelles. Matrice champ par
champ [à approuver](source-mapping-approval-matrix.md),
[contrats et propriété](source-mapping-contract.md),
[recette](source-mapping-preparation-validation.md).
DATA-01 et PAN-03 restent bloqués pour tout rapprochement réel et projection
financière ; une démonstration ne vaut pas approbation métier.

Correction imports/tableau de bord (2026-11-16) : l'accueil compose désormais
les indicateurs opérationnels CRM S16 et le compteur de clients autorisés.
Les lots affichent les blocages de publication et la provenance publiée.
Les snapshots ne sont toujours pas des clients/comptes : rapprochement,
autorité des champs et visibilité source par objet restent à approuver.
Voir [l'investigation et les mappings](import-source-mapping.md) et
[la validation Docker](import-dashboard-validation.md).

Mise à jour S16 : page d'activité commerciale CRM sur les interactions déclarées
et rendez-vous personnels par période/type/jour, avec stocks actuels de relances,
opportunités et brouillons personnels. Définitions et recette dans
[S16](migration/s16-commercial-activity.md). Aucun KPI financier, taux de
conversion ou accès managérial nouveau ; priorité suivante S17, matrice à valider.

Mise à jour S15 : segmentation descriptive étendue et complétude technique CRM
provisoire dans Panorama/Client 360, sans score KYC ni segmentation financière.
Dimensions disponibles, API, sécurité et résultats dans
[la recette S15](migration/s15-segmentation-quality.md). Âge, revenus, risque,
VIP et catégories produit validées restent indisponibles. Prochaine priorité :
activité commerciale et tableaux CRM managériaux, sous réserve des définitions.

Mise à jour S9 : worklist des relances prospects, vérifiée dans Docker ;
voir [le rapport S9](migration/s9-prospect-followups.md). Les résultats S8
ci-dessous restent l'historique de cette validation.

Mise à jour S10 : filtres descriptifs profession/secteur CRM dans le Panorama,
options/effectifs limités aux clients visibles ; voir
[le rapport S10](migration/s10-client-segmentation.md).

Mise à jour S11 : pipeline des opportunités existantes, lecture Commercial,
périmètre Client signé, navigation précise et édition existante ; voir
[le rapport S11](migration/s11-opportunity-pipeline.md).

Mise à jour S12 : agenda personnel Client & CRM, calendrier/liste/création/édition,
owner-only et heures Tunis explicites ; voir [la recette S12](migration/s12-manual-agenda.md).
Le [plan de remédiation du plafond S11](s11-pipeline-limit-remediation.md) est séparé,
sans modification du seuil dans cet incrément.

Revue du 15 novembre 2026. Les trois modules métier sont **Panorama Clients,
Pilotage Commercial et Pilotage Managérial**. L'analyse S7 utilisait à tort les
services techniques comme modules et omettait un bilan managérial distinct.
IAM et Data Integration sont transversaux. Les quatre services, leurs schémas et
propriétaires sont gelés ; aucune extraction ou restructuration n'est prévue.

Mise à jour S14 : COM-05 livre seulement les brouillons personnels de campagnes
dans Commercial, avec édition versionnée et audit/outbox. Les notes de ciblage
ne sont pas appliquées ; aucune cible, activation ou communication n'est livrée.
Voir [la recette S14](migration/s14-manual-campaigns.md).

## Sources et méthode

Comparaison de `cahier_de_charge.pdf` §§5–7 (pages PDF 4–6), §10/§12 (page PDF 11),
et `AICED.pdf` p.5–8 avec les routes React, vues/services DRF, modèles `clients`,
`commercial_store`, `integration_store` et migrations utilisées par Docker.
Les spécifications privées et leurs extractions restent exclues de Git.
Les manuels Carthago ne constituent pas un contrat d'accès ou de mapping.

« Livré » désigne une capacité précisément bornée vérifiée sur données
synthétiques par navigateur → Nginx → Django → PostgreSQL ; ce n'est ni une
recette AMEN INVEST ni un module complet. Une route, un modèle, un bouton
désactivé ou une maquette n'est pas une preuve. La recette réelle S8 et les tests
de contrat en processus sont distingués dans `migration/s8-functional-validation.md`.

## Panorama Clients

| Fonction attendue | État / écart constaté | Suite possible ou blocage |
|---|---|---|
| Répertoire, recherche, filtre physique/moral, pagination | Livré sur le CRM autorisé ; prospects exclus du panorama | Fonctionnel sur données AICED |
| Création/identité AICED, profil et coordonnées CRM | Livré : sauvegarde, relecture, édition concurrente 409 et audit transactionnel | Identité source non éditable |
| Fiche 360, provenance, interactions et opportunités | Livré pour les sections CRM ; fiche complète financière partielle | Données CRM autonomes disponibles |
| Comptes et produits détenus | Lecture locale autorisée livrée ; `FinancialAccount` contient référence, étiquette et date source, sans positions/valorisation | Projection synthétique explicite possible ; connecteur réel absent |
| CIN, revenus, âge, risque, connaissance bourse | Manquant des modèles/API métier ; cellules staging non rapprochées | Autorité champs sensibles, dictionnaire et contrat source nécessaires |
| Montant investi, portefeuille et historique financier | Manquant ; pas de quantités/prix/valorisation dans le modèle opérationnel | Source et calculs approuvés ; aucun montant réel fabriqué |
| Segmentation multicritère et graphiques | S10/S15 : type physique/moral, profession/secteur bruts, présence/absence, intervalle de complétude et champ CRM absent combinables avec recherche/tri/page ; options/effectifs du périmètre. Graphiques financiers absents | Aucun âge, revenu, VIP, risque ou catégorie produit inféré ; taxonomies et mappings à approuver |
| Qualité / complétude de profil | S15 : présence technique provisoire configurable, absences par champ et population, diagnostic de variantes sans fusion, détail Client 360 | Ni KYC ni validation métier ; sources externes non évaluables, corrections source bloquées ; approbation des champs et applicabilité physique/morale requise |
| Affectation/réaffectation | Référence et scoping existants ; aucune action métier publique de réaffectation | Workflow et responsabilités AMEN INVEST à définir |
| Scoring, rétention, client actif, valeur moyenne | Non implémentés ; « non calculé » n'est pas un indicateur | Formules, sources et seuils à approuver |
| Documents/pièces jointes | Manquant ; XLSX staging ≠ dossier documentaire | Rétention, classification, stockage et contrôles de contenu à cadrer |

## Pilotage Commercial

| Fonction attendue | État / écart constaté | Suite possible ou blocage |
|---|---|---|
| Rapport opérationnel d'activité | S16 : interactions et agenda personnel par période/type/jour ; relances, opportunités et brouillons personnels en stocks actuels distincts | Visibilité existante uniquement, sources propriétaires séparées ; ni activité d'équipe approuvée, ni historique de statuts, ni performance financière |
| Création/qualification de prospects physiques/moraux | Livré : source du contact, statut manuel, prochaine action/date, version | Pas de conversion source automatique |
| Interactions par fiche | Livré : appel, email, réunion/rendez-vous réalisé, visite, objet/notes/date ; création/édition auditée | Notes libres ≠ type « note » ; résultat/contact effectif non modélisés |
| Historique transversal | Livré S8 : recherche client/objet/notes, type, dates Tunis, pagination et lien fiche, compte rendu consultable | Création réelle → relecture → filtres/page → retour fiche vérifiés ; résultat commercial et prochaine action d'interaction restent absents |
| Opportunités par fiche | Livré : CRUD autorisé, estimation manuelle Decimal TND, ouvert/gagné/perdu, échéance, concurrence/révocation | Estimation commerciale ≠ encours ou revenu réalisé |
| Produit/responsable/prochaine action d'opportunité | Partiel : titre/notes/auteur/échéance, sans produit structuré ni responsable/action propre | Auteur ≠ commercial affecté ; catalogue et règles à valider |
| Pipeline transversal et évolution | S11 : Kanban paginé Ouverte/Gagnée/Perdue, recherche titre/notes/dossier, tri, compteurs autorisés et lien précis ; S13 : plafond global 500 retiré, autorisation Client par lots compacts, lecture à mémoire bornée vérifiée à 10 000 opportunités synthétiques | Coût linéaire et budget 4 s avec refus explicite ; débit sous charge réelle non certifié ; étapes/taux nouveaux à approuver, aucune probabilité calculée |
| Clients/prospects à relancer | S9 : worklist prospect avec échéances Tunis, recherche/statut/dates/tri/pagination et fiche ; pas d’action planifiée pour client | Sans priorité automatique, agenda ni notifications ; voir migration/s9-prospect-followups.md |
| Agenda et rendez-vous futurs | S12 : agenda personnel planifié, calendrier mensuel, liste paginée, création/édition, date/heures/types/notes, owner-only, UTC stocké/Tunis affiché ; Interaction réalisé inchangé | Chevauchements provisoirement autorisés ; équipe/participants/annulation/notifications et politique de fuseau finale à approuver |
| Notifications et rappels automatiques | Manquant ; bouton désactivé | Canaux, destinataires, consentement et règles à approuver ; aucun envoi S8 |
| Campagnes et ciblage | S14 : page personnelle de brouillons, nom/description/dates et notes préparatoires, recherche/tri/page, édition versionnée et audit/outbox Commercial | Aucun ciblage exécuté ni client associé ; propriété métier/affectation/partage, matrice, statuts, activation, communications et mesure à approuver ; voir migration/s14-manual-campaigns.md |
| Catalogue/offres/modèles d'emails | Manquant | Contenu et gouvernance AMEN INVEST avant diffusion |

## Pilotage Managérial

| Fonction attendue | État / écart constaté | Blocage réel |
|---|---|---|
| Accès direction, périmètre consolidé | Partiel : S17 `/pilotage-crm` utilise les scopes existants seulement ; pas de nouveau droit global ni de matrice DED/DG approuvée | Rôles de démonstration ≠ habilitations métier ; extension équipe/direction à approuver |
| Tableau de bord | S17 : cartes et graphiques opérationnels clients/types/complétude, interactions, relances, opportunités, rendez-vous et brouillons personnels ; sources/API vérifiées | Aucun KPI financier ou agrégat d'équipe implicite ; définitions techniques provisoires et périmètres collectifs à approuver |
| OPCVM par produit/client/commercial/période | Manquant ; pas de souscriptions/mouvements normalisés ni attribution commerciale | Sources, périodes, annulations et attribution à approuver |
| Comptes ouverts, libre/géré, conversions | Manquant du modèle opérationnel normalisé | Lien compte/tiers, dates et définition de conversion à valider |
| Encours/croissance/courtage/frais/rotation | Manquant | Mouvements/valorisation et formules indisponibles |
| Satisfaction/conformité/ratios CEA | Manquant | Sources, méthodes, seuils et autorité conformité à approuver ; pas de score LAB déduit |
| Tendances/comparaisons/exports | S17 : série quotidienne des interactions déclarées et débuts de rendez-vous, période/type bornés et tables accessibles ; pas d'évolution historique de stock, comparaison financière ou export managérial | Historisation, comparaison, périmètres direction et export à définir ; les jours sans enregistrement autorisé valent zéro, pas une performance déduite |
| Descriptif de l'activité CRM saisie | S16/S17 : reporting livré sur les périmètres existants, périodes et stocks distincts, sans nouveau droit de direction | Matrice managériale/équipe et attribution toujours à approuver ; ces comptages ne constituent pas des KPI de performance commerciale |

## Socle transversal conservé

Sessions/CSRF, révocation, signatures/anti-rejeu, isolation objet/organisation,
audit/outbox, sauvegarde/restauration et quatre historiques de migration sont
des garanties existantes. Import XLSX → staging → revue distincte → snapshot
immuable est livré sur données synthétiques. Il ne met à jour ni identité, ni
compte, ni portefeuille. Rapprochement et connecteur réel restent bloqués par le
contrat et la politique de propriété ; Carthago reste strictement read-only.

Le [backlog MVP](mvp-backlog.md) détaille priorités, valeur, effort, dépendances et
recette. Historiquement S8 livrait seulement l'historique transversal ; les
incréments S9–S17 et leurs limites sont désormais décrits ci-dessus. Les décisions
AMEN INVEST sont suivies dans [open-questions.md](open-questions.md).


Import review correction increment: see [workflow and verification](import-workflow-corrections.md) and [approval-only proposals](import-publication-approval-proposals.md). This improves reviewer navigation and truthful publication blockers; it does not approve operational source rules or activate Client 360 mappings. S16.1 intermittent pipeline HTTP 503 remains an open release risk.
