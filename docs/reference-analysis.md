# Analyse des références fournies

Inspection locale le 13 novembre 2026. Aucun document privé ni extrait contenant des données personnelles ne doit être versionné. Les fichiers temporaires sont dans `.local/reference-review/` (ignoré). `scripts/inspect_references.py` permet une nouvelle inspection locale. Mise à jour frontend : les 16 PDF interface ont ensuite été localisés dans `references/interface_aiced 2/`. Les pages Connexion, Tableau de bord et Panorama Clients ont été rendues et inspectées ; les mentions d'absence ci-dessous décrivent l'inspection initiale uniquement. Voir `frontend-design-system.md`.

| Source | Étendue observée | Conséquence |
|---|---|---|
| cahier_de_charge.pdf | 12 pages ; §§5–7 : CRM, commerce, pilotage ; §8 : assistance ; §§10–12 : confidentialité, planning, validations | Le scoring est explicitement à définir (§5.4). Les modèles prédictifs et seuils d'engagement restent à valider. Les droits détaillés ne sont pas fournis. |
| AICED.pdf | 12 pages ; trois modules p.5, panorama p.6, commercial p.7, pilotage p.8, gouvernance p.9–10 | Modèle 3P confirmé ; SICAV/FCP/Bourse et comptes libres/gérés sont une terminologie métier, pas un contrat de calcul. La vision restreint le pilotage à DED/DG sans matrice finale. |
| Carthago Référentiel | 90 pages ; devises, frais, valeurs, tiers, comptes | Séparer référentiels, tiers et relations de comptes ; manuel utilisateur, pas schéma physique ni API. |
| Carthago Titres | 193 pages ; ordres, instructions titres/espèces, transferts, opérations, tableaux de bord | Workflows transactionnels externes ; AICED n'exécute aucune de ces mutations. Ne pas confondre consultation CRM et logiciel de tenue de titres. |
| Administration sécurité | 16 pages ; groupes métier/organisationnels p.6, utilisateurs, profils/habilitations | Séparer rôle fonctionnel et appartenance organisationnelle ; ne pas importer automatiquement les droits Carthago. |
| LAB | 15 pages ; matrice classification/activité/pays, tiers physiques/moraux, listes, dormance, FATCA | Risque LAB différent du potentiel commercial et de l'engagement. Aucune reproduction du calcul ou action LAB sans autorité métier. |

Inspection visuelle effectuée sur pages rendues : AICED p.6, Référentiel p.6/53/58/67 (tiers physiques, moraux et comptes titres), Titres p.9 (ordres), Sécurité p.6 et LAB p.6. Les captures montrent présentations et interfaces Carthago ; les styles Carthago ne sont pas retenus comme maquettes AICED. Les 16 écrans AICED annoncés ne sont pas présents. L'extraction de texte des six PDF a été produite ; la revue est ciblée sur le cadrage et les workflows pertinents au socle, sans prétendre une recette exhaustive des centaines de pages.

## Structures Excel réellement observées

Dimensions incluant l'en-tête et les cellules formatées ; elles ne prouvent pas le nombre de clients valides.

| Classeur | Feuille | Dimensions | Champs structurants |
|---|---|---|---|
| Compte titre.xlsx | Compte titre | A1:AO100 (41 colonnes) | B Agence UIB, C Fréquence du reporting, D Détenteur du compte, E Numéro de compte (espace final), I Date d'ouverture, J CEA, K Pack de frais, AH Identifiant, AI Type de gestion, AJ Catégorie d'avoirs |
| Tier Personnes Physiques.xlsx | Tier | A1:AG2341 (33 colonnes) | B Identifiant, C Nom, D Prénom, G Type de pièce d'identité, H N° de pièce d'identité, I Date de naissance, U Risque LAB/FT, AC Identifiant (doublon d'en-tête) |
| Tier Personnes Morales.xlsx | Tier | A1:Y843 (25 colonnes) | B Identifiant, C Libellé Court, D Libellé Long / Raison Sociale, F Chargé client, K Secteur d'activité, S Risque LAB/FT |

Les trois ont une colonne A sans libellé. Les lignes échantillonnées utilisent largement des cellules texte avec format General, y compris des dates : un type date natif ne peut pas être présumé. Les coordonnées et identifiants ne sont pas reproduits ici. Aucun parsing d'import n'est implémenté au socle ; les structures nécessitent des mappings par position et un dictionnaire métier approuvé.

## Écarts et préséance
La vision présente trois modules ; le cahier ajoute l'IA comme quatrième axe. Le brief ajoute ingestion, rapprochement et administration : ils sont traités comme modules transversaux. Le planning de trois mois est une intention, pas une garantie de livraison de toute l'IA. Le brief impose lecture seule Carthago et sécurité dès le départ : ces contraintes priment sur les écrans de saisie Carthago des manuels. Questions non résolues : `open-questions.md`.
