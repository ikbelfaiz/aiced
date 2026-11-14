# Ingestion et rapprochement

Statut courant : import manuel XLSX implémenté avec staging et publication de snapshots immuables ; voir `import-templates.md` et `client-360-data-management-status.md`. Les règles et clés sont approuvées explicitement à deux acteurs. Aucun rapprochement ni mise à jour métier source n'est autorisé par ces règles. Le contrat automatique Carthago et la publication vers clients/comptes restent bloqués. Les limites réellement appliquées sont 10 Mio/25 Mio, 1 000 entrées ZIP, ratio 200 et 50 000 lignes ; elles remplacent les seuils proposés ci-dessous.

`ManualExcelSource` et `CarthagoReadOnlySource` produiront le même contrat. Le second lève explicitement une erreur tant qu'une interface n'est pas approuvée. Aucun endpoint, table ni identifiant de connexion Carthago n'est supposé.

Pipeline : upload privé → validation fichier → choix modèle/version et mapping par position → normalisation → staging → erreurs et doublons → propositions de rapprochement → approbation selon politique → publication transactionnelle → historique et rapport des rejets. Aucun upload ne modifie immédiatement un client.

Les modèles distincts sont tiers physique, tiers moral et compte titres. Les en-têtes et particularités observés sont dans `reference-analysis.md`. Modèles versionnés, contrôles de champs obligatoires, types et relations après approbation métier. Les dates texte ambiguës sont rejetées ; les identifiants numériques ne sont pas convertis aveuglément. Conserver numéro de ligne, position de colonne, valeur source privée et valeur normalisée. Pas de formule exécutée ; pas d'évaluation par Excel/LibreOffice côté serveur.

Limites initiales proposées à valider : 10 MiB compressés, 100 MiB décompressés, 50 000 lignes, nombre borné d'entrées ZIP et ratio de compression. Contrôler signature ZIP/OOXML, absence de macro/liens externes, XML sûr, feuilles attendues, colonnes en double et dimensions excessives. Rejeter les formules même si une valeur en cache existe. Noms de fichiers générés côté serveur ; téléchargement de rejets protégé et valeurs échappées contre injection de formule CSV. Ne jamais servir un fichier fourni comme HTML.

## Identités et propriété
Une clé externe vérifiée et unique peut proposer un lien déterministe sous politique approuvée. Nom, téléphone ou similarité ne produisent que des propositions. Identité incertaine et conflit de champs exigent revue humaine. Un prospect AICED seul est un état normal. Distinguer matched, aiced_only, source_only, pending_identity, potential_duplicate, field_conflict, missing_source et resolved.

Une absence ne crée un cas missing_source que pour un snapshot déclaré complet, de même périmètre et comparable en date. Elle ne supprime jamais le client. Un export partiel ne prouve aucune disparition. Les exports hors ordre temporel ne remplacent pas les données plus récentes sans revue.

Règles d'autorité versionnées : données financières source-owned en lecture seule, notes/relations commerciales CRM-owned ; identités conflictuelles contrôlées. Sans politique approuvée, publication source bloquée. Aucune correction sortante vers Carthago.

## Idempotence et concurrence
Empreinte SHA-256, source, organisation, modèle/version, nature snapshot, date d'effet et mapping composent la clé de lot. Même lot rejoué : résultat existant, sans nouvel effet. Contraintes uniques sur clés source ; verrouillage du lot et du cas ; contrôle de version lors d'une décision. Publication et audit dans la même transaction. Une erreur provoque rollback, les rejets restent dans staging pour revue ; pas de succès fictif ni de publication financière partielle implicite.
