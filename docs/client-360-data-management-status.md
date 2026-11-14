# Client 360° et Gestion des données

## Périmètre livré

`/clients/:id` : fiche backend réelle, identité et origine, profil CRM, comptes source en lecture seule, interactions et opportunités paginées. Création de personnes physiques/morales AICED depuis le panorama, modification d’identité AICED non liée à une source, email/téléphone/profession/secteur/notes CRM, création et modification des interactions réalisées et estimations commerciales. Aucun score, agrégat financier ou contenu IA inventé. Estimations commerciales actuellement saisies en TND, décimal à trois places ; jamais assimilées aux encours source.

`/gestion-donnees` : contexte des organisations autorisées, dépôt XLSX brut avec CSRF, modèles versionnés, choix explicite de date, preview paginée par position, erreurs et avertissements, rapport CSV, historique des lots et audit, proposition/approbation/révocation des règles et revue de publication. Voir `import-templates.md` pour le schéma réellement inspecté et les limites.

**La publication ne synchronise pas les clients ni les comptes : elle publie des snapshots source immuables.** Le sens du double Identifiant et la relation comptes/tiers n’ont pas été approuvés. Aucun domaine Carthago n’est modifié. Aucune interface Carthago externe n’est inventée ou activée. Le statut UI reste « non connecté », avec dernière situation locale autorisée si disponible.

## Autorisations

Intersection de `clients.view` et des capacités objet pour toute lecture/écriture. `clients.create` et lecture au scope organization pour créer un nouveau client. `clients.update_identity` uniquement si origine AICED et absence de lien externe ; identité source et comptes non modifiables. `clients.update_crm` limite les champs aux données commerciales nommées AICED. `interactions.view/manage` et `opportunities.view/manage` distinctes, intersectées sur le même client. Champs inconnus, organisation, propriétaire ou provenance injectés dans un corps sont refusés.

Import : `imports.view` et `clients.view_financial` au scope organization dans **la même organisation**, plus `imports.upload`, `imports.approve` ou `imports.policy_manage` selon l’action. IT, flags Django staff/superuser et permissions réparties entre organisations ne confèrent aucun accès implicite. Les UUID de lots, règles, activités et clients sont revalidés dans le périmètre.

Écritures sérialisées par organisation, relecture des grants après verrou, version obligatoire sur les modifications, audit dans la transaction. Les éditeurs conservent la version ouverte même lors d’un rafraîchissement en arrière-plan. Changer de client remonte le composant et ferme l’éditeur précédent. Le vieux endpoint notes-only `/crm/` reste compatible et incrémente la version ; il ne constitue pas un éditeur générique de champs source.

## Référence visuelle et écarts

Le PDF `04 · Karim Ben Youssef.pdf` a été rendu et inspecté visuellement, puis comparé aux captures API synthétiques. Structure reprise : header, badges, onglets, trois cartes Profil/Portefeuille/Relation, puis Interactions/Assistant ; jetons existants, sidebar 232 px, header 76 px. Captures privées dans `.local/ui-review/screens/client-360*.png` et `data-management*.png`, référence `.local/ui-review/04-1.png`.

Écarts intentionnels : identité réelle du dossier synthétique, absence de VIP/score/encours/répartition sans source validée, saisie CRM clairement séparée des champs source, création d’une interaction réalisée plutôt qu’agenda non implémenté, assistant et documents indisponibles. Data Management adapte le design system : aucune maquette dédiée n’est fournie. Comparaison humaine desktop et mobile, pas de certification pixel ; police Inter approximative.

## Vérification reproductible

Environnement local PostgreSQL isolé ; uniquement fixtures et comptes synthétiques. Aucune donnée des trois classeurs de référence n’a été chargée dans la base.

- `python scripts/backend_check.py migrate --noinput`
- `python scripts/backend_check.py makemigrations --check --dry-run`
- `python scripts/backend_check.py check`
- `python scripts/backend_check.py spectacular --file .local/frontend-schema.yaml --validate --fail-on-warn`
- `python scripts/backend_check.py test core identity clients ingestion audit --noinput`
- `npm --prefix frontend run build`
- `python scripts/frontend_e2e.py --grep-invert 'production build'`
- `python scripts/frontend_e2e.py --production --grep 'production build|Client 360|Data Management'`

Résultats vérifiés le 13 novembre 2026 : **83 tests backend PostgreSQL réussis**, **9 scénarios Chromium développement réussis**, **4 scénarios Chromium sur le build production réussis** (aperçu fictif désactivé, éditeur concurrent, Client 360 et import complet à deux acteurs). Build TypeScript/Vite réussi ; deux avertissements non bloquants sur annotations de commentaires Zod. `check`, migrations à jour, absence de migration manquante et schéma OpenAPI validé sans avertissement. `npm audit --omit=dev` : zéro vulnérabilité connue signalée ; ce n'est pas un audit exhaustif Python/infrastructure.

Les tests incluent isolation/finance/champs, source read-only, validation, versions et éditeur concurrent, audit rollback, formats de date, fichiers malformés, ZIP/XML dangereux, doublons, permissions insuffisantes, quotas, publication partielle explicite et concurrence/idempotence. Les contraintes SQL vérifient également la cohérence des états d'approbation/publication. Rapports privés : `.local/workspace-backend-tests.log`, `.local/browser-report.json`, `.local/browser-production-report.json`.

Problèmes corrigés pendant vérification : mauvais nom de champ dans la lecture d'audit ; validation du nom complet pouvant dépasser 200 caractères ; « Update User » pris à tort pour une date ; version d'éditeur pouvant dériver après rafraîchissement ; routes de détail limitant désormais les méthodes HTTP acceptées ; test d'idempotence corrigé pour rejouer les mêmes octets XLSX plutôt que régénérer un ZIP horodaté différent. Le focus après fermeture de dialogue revient au contenu si le bouton d'ouverture est devenu indisponible. Le sélecteur de fichier est affiché en français et borné sur mobile. L'aperçu fictif est limité aux deux pages de comparaison en lecture seule : il ne peut étiqueter les pages d'édition Client 360/import comme fictives.

Pour les tests UI, `seed_workspace --confirm-synthetic` crée séparément `synthetic.operator.a` et `synthetic.reviewer.a`, sans élargir les rôles Phase 1. DEBUG et mot de passe synthétique via variable privée requis. Le runner génère son XLSX synthétique sous `.local/`, ne journalise pas le password et n’enregistre pas de trace contenant les requêtes d’authentification. Ses seuls serveurs temporaires relèvent les budgets de tentatives et quotas pour autoriser les répétitions ; les tests backend vérifient les limites ordinaires. Aucun rôle production ni approbation métier n’est provisionné.

## Limites restantes

Rapprochement et publication vers les entités métier bloqués sans mapping/propriété approuvés ; comptes/positions complets, métriques/segmentation, identité sensible, agenda, pièces jointes et IA hors périmètre. Aucun connecteur Carthago. Retention/purge, recette métier des rôles et champs, limites de charge, processus opérateur et durcissement de production restent à valider. Les uploads bornés sont synchrones ; pas de file de tâches ni antivirus intégré. L’autorité d’approbation métier réelle n’est pas remplacée par les rôles de démonstration.
