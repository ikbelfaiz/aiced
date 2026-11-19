# Répétition de déploiement — candidat 36fb5f9

## Statut : bloqué sur une restauration représentative

Le 19 novembre 2026, aucun backup de la cible accompagné d'une identification
et d'une autorisation de recette n'a été fourni ou identifié. Les archives de
`.local/` et le projet Docker `aiced-test` sont des artefacts de recette
synthétique ; leur existence ne démontre pas qu'ils représentent les données,
volumes, versions, privilèges ou conditions opérationnelles de la cible.
La répétition sur une restauration représentative, la qualification de la
restauration cible et l'acceptation de déploiement restent donc bloquées.
Aucune base de production n'a été utilisée et aucun déploiement n'a été effectué.

## Vérifications synthétiques complémentaires

- Candidat vérifié : `36fb5f9`. Projet Docker de test isolé, PostgreSQL 17.12,
  base source portant le marqueur `aiced-s7-synthetic-only`.
- Un `pg_dump -Fc` de cette base a été restauré avec `pg_restore --exit-on-error`
  dans une nouvelle base nommée de manière unique sur le cluster de test. Aucune
  base existante n'a été remplacée ou supprimée. Le nom local de la restauration
  et le script de vérification sont conservés sous `.local/compose-test/`.
- Les agrégats comparés entre source et restauration correspondent : 96 lots
  publiés avec règle historique, 7 lots publiés en configuration fixe, 103
  snapshots, 103 journaux de publication et 103 entrées outbox correspondantes.
  Cette comparaison vérifie ces totaux uniquement ; elle ne constitue pas une
  comparaison exhaustive des contenus, permissions ou données de la cible.
- La restauration contient l'historique `integration_store.0006` et le rôle
  runtime possède le grant UPDATE sur la colonne fixe. L'exécution réelle de
  `migrate integration_store 0005_reusable_publication_rules` sur cette seule
  restauration a échoué sur la contrainte historique attendue. La transaction a
  préservé les sept publications fixes et l'enregistrement de la migration 0006.
  La restauration de la sauvegarde post-publication permet une reprise avec un
  code compatible ; elle ne prouve pas la récupération d'écritures ultérieures.
- Les essais précédents sur cette même stack synthétique ont réussi : 253 tests
  backend ; quatre scénarios navigateur incluant les trois classeurs, la revue
  indépendante et l'historique ; contrôles gateway, snapshot et journal/outbox.
  La migration `ingestion.0009` a été exécutée lors de la création de la base
  de tests backend ; `integration_store.0006` lors de l'initialisation Integration.
  Ces résultats ne remplacent pas une migration sur restauration représentative.

## Éléments requis pour lever le blocage

Obtenir une sauvegarde de cible autorisée et représentative, les versions et
propriétaires de schéma, les rôles réels, les volumes et les critères d'acceptation.
Restaurer exclusivement dans une infrastructure jetable distincte, confirmer
sa provenance, comparer les lots historiques et l'audit avant/après migration,
répéter les migrations et grants applicables à chaque cible distincte, les trois
imports, la séparation des acteurs et la restauration après publication. Mesurer
les durées et tester la stratégie de reprise et de réconciliation des écritures
selon [la procédure préparée](fixed-configuration-deployment.md). La migration
inverse ne doit jamais être tentée sur des données de production.

## Priorité fonctionnelle proposée

La prochaine priorité CRM est DATA-01 : préparer l'affichage en lecture seule
des snapshots publiés dans Client 360 après approbation du rapprochement et des
droits par objet et par champ. Le choix utilisateur de B pour les personnes
physiques est acquis ; il ne confirme pas les relations compte/tiers, l'unicité
inter-source, la propriété des champs ni la visibilité financière. Ces décisions
restent nécessaires avant toute association réelle ; le défaut intermittent 503
du pipeline demeure en parallèle un risque de livraison ouvert.
