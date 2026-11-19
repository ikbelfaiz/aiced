# Déploiement préparé : configurations fixes des imports

Cette procédure est une préparation, pas une preuve de préparation à la production.
Elle concerne uniquement AICED ; aucune écriture Carthago. Les anciennes règles,
approbations, snapshots, liens de lots et journaux sont conservés. Le nouveau
parcours exige toujours un réviseur distinct du déposant. Les lots historiques
non classifiés utilisent une règle historique approuvée et active uniquement si
elle est compatible et unique ; sinon redéposer le fichier avec un usage explicite.

## Prérequis et ordre

1. Répéter sur une restauration isolée représentative, contrôler la sauvegarde et
   sa restauration, identifier explicitement la base, le schéma, le propriétaire
   et le rôle runtime Integration. Planifier une interruption des écritures
   d'import pendant la migration, le grant et le changement de version.
2. Vérifier la version applicative, les historiques Django et l'absence d'une
   autre migration concurrente. Sur la cible quatre services, exécuter les
   migrations avec les paramètres existants du service Integration et son rôle
   propriétaire/migrateur : `python manage.py migrate integration_store 0006_fixed_configuration`.
   Le schéma propriétaire attendu est `aiced_integration`. Le monolithe historique,
   s'il est réellement une cible distincte, utilise ses propres paramètres et
   `python manage.py migrate ingestion 0009_fixed_configuration` ; ne pas exécuter
   les deux historiques sur la même table. Les migrations ajoutent une colonne
   nullable et remplacent une contrainte, sans modifier les lots préexistants.
   Vérifier le verrouillage et la durée sur la restauration avant intervention.
3. Sur la base Integration migrée, en tant que propriétaire habilité, exécuter
   `psql -X -v ON_ERROR_STOP=1 -v integration_runtime_role=ROLE_RUNTIME -f infra/deployment/fixed_configuration_grant.sql`.
   Remplacer `ROLE_RUNTIME` par le rôle runtime existant, contrôlé hors de ce
   document. Le script échoue si le rôle ou la colonne n'est pas approprié et ne
   donne que UPDATE sur cette colonne ; le répéter ne crée aucun grant dupliqué.
   Il ne retire pas des privilèges déjà accordés. Les autres grants historiques
   nécessaires au service doivent déjà être présents.
4. Déployer ensemble les versions compatibles Integration, API et frontend,
   puis effectuer les contrôles ci-dessous avec des acteurs et données de recette
   autorisés, avant de rouvrir les imports. Ne pas publier un lot métier réel
   comme simple smoke test sans autorisation métier.

## Vérifications SQL et applicatives

Avec `:runtime` remplacé par le nom vérifié du rôle runtime :

```sql
SELECT app, name, applied FROM aiced_integration.django_migrations
 WHERE app = 'integration_store' AND name = '0006_fixed_configuration';
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
 WHERE conrelid = 'aiced_integration.ingestion_importbatch'::regclass
   AND conname = 'import_publication_consistent';
SELECT has_column_privilege(:'runtime', 'aiced_integration.ingestion_importbatch',
                            'fixed_configuration_version', 'UPDATE');
SELECT count(*) AS incoherents FROM aiced_integration.ingestion_importbatch
 WHERE status = 'published' AND ((policy_id IS NULL) = (fixed_configuration_version IS NULL));
```

Attendus : migration présente, contrainte mise à jour, privilège vrai, zéro ligne
incohérente. Sur le monolithe, employer son schéma et son historique Django, et
vérifier ses privilèges propres ; le script Integration ne s'y applique pas.
Vérifier également absence de droits de table excessifs, état de santé et accès
inter-organisations, rejet de l'auto-publication, aperçu/rejets, publication par
réviseur distinct et journal/outbox, et conservation d'un lot historique approuvé.
Vérifier les types de fichier et les deux formats de dates avec données synthétiques.

## Reprise et retour arrière

Avant toute publication fixe, arrêter les écritures, vérifier l'absence de lots
publiés avec `fixed_configuration_version IS NOT NULL`, puis répéter sur la
restauration une marche arrière de code et de migration. Conserver le grant si
nécessaire jusqu'à la fin de l'opération ; sa révocation ciblée éventuelle est
`REVOKE UPDATE (fixed_configuration_version) ON aiced_integration.ingestion_importbatch FROM ROLE_RUNTIME`.
Après avoir arrêté les écritures et vérifié l'absence de publications fixes, les
commandes inverses sur les cibles respectives sont `python manage.py migrate
integration_store 0005_reusable_publication_rules` et, uniquement pour la cible
monolithique distincte, `python manage.py migrate ingestion
0008_reusable_publication_rules`. Elles suppriment la nouvelle colonne : toute
valeur qu'elle contient serait perdue ; vérifier aussi son absence sur les lots
staged avant de les exécuter. Utiliser les mêmes paramètres et rôle migrateur que
pour l'aller, puis restaurer le code compatible et vérifier les grants et la santé.
Une fois des publications fixes enregistrées, l'ancienne contrainte exige un
`policy_id` et le retour direct ou la migration inverse échoueraient : ne pas
fabriquer de règle ni supprimer des lots. Arrêter les écritures, préserver la
base et l'audit, et choisir une reprise compatible ou une restauration testée
avec traitement explicite des écritures intervenues depuis la sauvegarde.
Ne jamais revenir à un ancien code en écriture sur des données non réconciliées.
