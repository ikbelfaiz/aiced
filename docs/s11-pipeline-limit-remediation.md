# Plan de remédiation — limite S11 de 500 dossiers

Statut historique S12 : **plan séparé, non implémenté en S12**. Le seuil S11 et
son refus 503 au-delà de 500 références restaient actifs à cette étape.
**S13** implémente une variante bornée, sans privilège TEMP ni fusion top-K
dépendante de l'offset : curseur Commercial ordonné, autorisation Client
compacte, barrières et budget de 4 s. Voir les mesures, critères réellement
testés et limites dans [la recette S13](migration/s13-pipeline-scalability.md).
Le plan initial ci-dessous est conservé comme historique des options évaluées.

## Problème précis

Le pipeline énumère les références de dossiers présentes dans Commercial, puis
demande à Client leur autorisation par lots signés de 100. Le plafond global
borne le fan-out mais peut refuser un petit portefeuille autorisé quand beaucoup
de références non visibles existent ailleurs. Un simple relèvement augmente
la latence et les durées de transaction sans résoudre cette dépendance.

## Proposition dans les frontières actuelles

1. Mesurer sur des jeux synthétiques : 500, 501, 2 000 puis 10 000 références,
   avec peu/beaucoup de dossiers visibles, plusieurs organisations, prospects,
   droits assignés, titres identiques, dates absentes et mutations concurrentes.
   Relever requêtes SQL, appels HTTP, mémoire, p95 et latence de révocation.
2. Ajouter un contrat privé Client paginé par curseur/keyset qui énumère **les
   dossiers autorisés** avec ID, nom et possibilité d'édition, sous l'intersection
   actuelle clients/opportunités/prospects. Lots de 100, mêmes HMAC/audience,
   nonces, session et refus par défaut. Aucun filtre de scope fourni librement
   par le navigateur, aucun accès Commercial aux tables Client/IAM.
3. Commercial consomme ces lots et interroge uniquement son stockage pour les
   opportunités correspondantes. Combiner les effectifs exacts par statut et
   le classement global, avec départage UUID, avant de produire la page publique.
   Recherche par nom et titre/notes conserve sa sémantique actuelle. Aucun miroir
   durable de propriété/affectation ni cache d'autorisation n'est requis.
4. Prototyper deux implémentations internes, puis choisir après mesure : agrégats
   et fusion des résultats par lots en mémoire bornée ; ou travail temporaire
   strictement local à la transaction Commercial si le volume impose un tri
   externe. Vérifier les permissions nécessaires avant de retenir la seconde.
   Aucun nouveau service, schéma propriétaire ou outil de messagerie.
5. Garantir un périmètre cohérent pendant le parcours : étudier l'admission de
   lecture avec les barrières IAM/Client existantes et/ou un jeton de révision
   de scope vérifié avant réponse. Ce point doit être démontré par tests de
   courses avant codage définitif. Ni curseur ni jeton ne doit devenir une
   autorisation réutilisable après révocation. Les RPC restent sans verrou
   bloquant détenu par le serveur Client, pour éviter les interblocages.
6. Fixer un budget global de requête et de mémoire à partir des mesures, avec
   marges sous le timeout Gateway. Dépassement ou changement de scope : refus
   explicite sans réponse partielle. Conserver la forme et l'exactitude de
   `count`, `statuses`, `results`, pagination et tris publics ; toute alternative
   incompatible doit faire l'objet d'une décision API distincte.

## Critères de sortie

- Plus de 500 références, dont une majorité invisible, n'empêchent plus la lecture
  d'un portefeuille autorisé tant que le budget mesuré est respecté.
- Parité exacte avec un oracle synthétique pour recherche/statuts, ordre global,
  pages, égalités et sommes des effectifs ; aucune duplication ni omission.
- Anonyme, IT, capacités séparées sur des objets distincts, scopes assignés,
  prospects, révocation de rôle/utilisateur/session et réaffectation concurrente
  ne révèlent aucune ligne, nom ou statistique hors périmètre.
- Signature invalide, rejeu, curseur altéré/réutilisé par un autre acteur, panne
  IAM/Client, réponse trop volumineuse et timeout ferment l'accès.
- Aucun modèle Client/IAM chargé par Commercial ; aucun changement d'ownership.
  Tests régression/OpenAPI, navigateur et arrêts réels Docker passent.
- Le benchmark démontre une latence de révocation acceptable ; retirer le seuil
  500 seulement après satisfaction de ces critères et revue des mesures.

Le plan traite un défaut technique borné ; il ne dépend d'aucune nomenclature,
source Carthago, règle de score ou migration architecturale. Il peut constituer
le prochain incrément technique autonome, avant une montée en volume réelle.
