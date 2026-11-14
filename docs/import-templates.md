# Schémas Excel inspectés et contrat d’import v1

Inspection locale des trois références, sans import de leurs données dans PostgreSQL. Les en-têtes complets et positions sont transcrits dans `backend/ingestion/templates.py`. `scripts/inspect_excel_schema.py` produit les métadonnées de types sous `.local/ui-review/excel-schema.json`, sans exporter de valeur d’enregistrement. Les références, extractions et uploads ne sont pas versionnés.

| Fichier | Feuille unique | Dimensions observées | Particularités vérifiées |
|---|---|---|---|
| Tier Personnes Physiques.xlsx | Tier | 2 341 × 33, en-tête compris | A sans libellé ; B et AC portent tous deux « Identifiant » ; C Nom, D Prénom, E Nom Complet ; I Date de naissance ; U Risque LAB/FT. B et AC contiennent du texte. Aucun choix implicite entre ces deux identifiants. |
| Tier Personnes Morales.xlsx | Tier | 843 × 25 | A sans libellé ; B Identifiant (texte), C Libellé Court, D Libellé Long / Raison Sociale ; S Risque LAB/FT. Les champs Sexe/Civilité/État Civil restent conservés sans les transformer en attributs de personne physique. |
| Compte titre.xlsx | Compte titre | 100 × 41 | A sans libellé ; E « Numéro de compte » avec espace final dans l’en-tête ; D Détenteur du compte ; I Date d’ouverture ; AH Identifiant ; AI Type de gestion ; AJ Catégorie d’avoirs. Aucun encours, prix, quantité ou devise exploitable n’est fourni par ce schéma. |

Dates observées : chaînes `##/##/####` pour les dates de naissance et d’ouverture, et `##/##/#### ##:##:##` pour Creation Date des comptes. Les Creation Date des tiers sont vides dans les références inspectées. Une forme de texte ne prouve pas à elle seule l’ordre jour/mois : le dépôt propose ISO ou DMY explicitement, et la règle approuvée de publication doit reprendre le même choix. Les dates Excel natives sont acceptées. Le champ « Update User » est du texte, jamais une date malgré le mot Update.

## Validation technique

En-têtes exacts par position, y compris doublons et espace final, une seule feuille attendue. Les clés candidates sont B/AC (physiques), B (morales), E (comptes). La règle approuvée fixe la colonne retenue. Aucun lien automatique compte/tiers ni fusion par nom. Les identifiants numériques sont rejetés pour préserver les zéros initiaux ; aucune conversion implicite.

Dates ISO ou DMY explicites (et heure facultative pour DMY), dates impossibles, dates de naissance futures et dates postérieures à la situation source déclarée rejetées. Le texte source est conservé ; `normalized_dates` contient une représentation ISO distincte, sans supposer le fuseau des timestamps source sans offset. Les champs métier requis au-delà de la clé ne sont pas inventés : « validée fichier » ne signifie pas « identité rapprochée » ou « client publiable ».

Fichier limité à 10 Mio compressés, 25 Mio décompressés, 1 000 entrées ZIP, ratio 200 et 50 000 lignes. ZIP/OOXML corrompu, chemins dangereux, entités XML, chiffrement, macros, objets incorporés, liens externes, colonnes excédentaires, erreurs Excel et formules sont refusés au niveau fichier ou ligne selon le contrôle. Aucun moteur Excel ne s’exécute. Rejets : numéro de ligne, positions, valeurs sources et erreurs ; CSV protégé contre l’injection de formule et téléchargé comme pièce jointe.

Tous les doublons internes sur une clé candidate sont rejetés, sans « première ligne gagnante ». Une clé déjà publiée dans la même organisation et le même modèle génère un avertissement : une nouvelle version source peut être publiée après revue, sans écrasement de l’historique. Un replay des mêmes octets, organisation, modèle/version, date source, nature et format de date retourne le même lot. Un fichier réexporté avec d’autres octets est une nouvelle version de lot, pas un replay binaire.

## Publication et autorité

La seule règle implémentée publie des **snapshots immuables**. Elle n’autorise aucune modification de Party, d’identité externe ou de FinancialAccount. Création de règle avec justification et clé/date explicites ; approbateur différent du créateur ; révocation possible, aucune édition silencieuse de règle approuvée. Publication par un acteur différent du déposant, avec capacité explicite ; exclusion des rejets obligatoirement confirmée. Sans ligne valide ou règle approuvée correspondante, aucun effet.

Organisation verrouillée puis habilitations relues ; publication et audit dans une transaction. Une panne provoque un rollback intégral ; le staging reste consultable. Replays et publications concurrentes n’ont qu’un effet. PostgreSQL interdit UPDATE/DELETE des lignes staged et snapshots. Historique, empreinte et politique retenue sont conservés ; aucune suppression par absence d’un export, même déclaré complet.

Limites techniques configurables : 20 lots en staging et 50 nouveaux lots par jour/organisation (`IMPORT_MAX_STAGED_BATCHES`, `IMPORT_MAX_DAILY_BATCHES`). Les replays existants restent permis. Purge/rétention, chiffrement des sauvegardes et quotas d’infrastructure restent à valider pour production.
