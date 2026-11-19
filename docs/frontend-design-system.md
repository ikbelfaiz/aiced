# Stratégie frontend

Agenda : la maquette « 08 · Agenda commercial » a été inspectée visuellement.
L'interface propose une semaine sur sept jours, un calendrier mensuel et les
rendez-vous personnels existants. Le tableau s'étend aux horaires réellement
enregistrés ; au-delà de trois chevauchements ou de 50 rendez-vous par jour,
la liste paginée reste accessible. Le calendrier défile horizontalement sur
mobile. Aucun agenda collectif, rappel urgent ou statut réalisé n'est inventé.

Pipeline : la maquette « 07 · Pipeline des opportunités » a été inspectée
visuellement. La page reprend ses colonnes gris clair, cartes blanches, badges,
montants, échéances et filtres, adaptés au mobile. Elle conserve les trois
statuts réellement disponibles (ouvertes, gagnées, perdues), la pagination et
les estimations existantes ; aucun nouveau stade commercial ou total financier
n'est déduit de la maquette.

Tableau de bord API : après inspection visuelle de la maquette « 02 · Tableau de
bord », la grille de cartes et de graphiques utilise les données CRM autorisées :
clients par type, statuts d'opportunités, interactions quotidiennes, relances et
brouillons personnels. La courbe représente les interactions des 30 derniers
jours, pas une évolution du nombre de clients. Les segments métier, encours et
taux de rétention restent explicitement indisponibles ; aucune valeur ni règle
financière n'est inventée. Les sources échouées n'affichent pas de valeurs périmées.

Tranche prospects du 14 novembre 2026 : PDF 06 rendu (`.local/ui-review/06-1.png`) puis inspecté visuellement. `/prospects` reprend sidebar, titre, bouton vert, grille de quatre cartes, recherche/filtres et table. Comparaison des captures desktop 1440 px et mobile 390 px ; correction du chevron de filtre et de l'espacement de 24 px entre filtres et table. Responsive adapté sans maquette mobile ; aucun score de fidélité pixel revendiqué. Les valeurs proviennent uniquement de l'API et des fixtures synthétiques, jamais des personnes illustrées dans le PDF. Les scores, taux de conversion, export et filtres métier non approuvés ne sont pas simulés comme fonctionnalités. La qualification manuelle, la prochaine action, la fiche, les interactions et les opportunités sont fonctionnelles dans le périmètre autorisé.

Extension suivante livrée : Client 360° (`/clients/:id`) et Gestion des données (`/gestion-donnees`), création et édition CRM AICED. La page 04 Karim a été rendue et comparée aux captures ; les onglets/champs source indisponibles restent explicites. La portée actuelle et ses limites sont dans `client-360-data-management-status.md` ; les descriptions « futures/non implémentées » ci-dessous concernent la phase des trois premiers écrans.

Les 16 PDF sont disponibles dans `references/interface_aiced 2/` (privé, ignoré). Les pages uniques de Connexion (1440 × 1080), Tableau de bord (1440 × 1231) et Panorama Clients (1440 × 1272) ont été rendues avec PyMuPDF et inspectées visuellement. Les captures de référence restent dans `.local/ui-review/01-1.png` à `03-1.png`.

Jetons partagés dans `frontend/src/styles.css` : marine `#1d3c79`, bleu `#1d4695`, vert `#299d49`, texte `#222222`, secondaire `#6b7280`, bordure `#e5e7eb`, fond `#f5f6f8`, rayon cartes 12 px. Sidebar 232 px, en-tête 76 px, marge principale 32 px. Police Inter locale (approximation visuelle : les PDF utilisent une police Type3 sans famille exploitable). Aucun appel à une police externe.

Organisation implémentée : `app` (routeur/gardes), `components/ui` (Button, Dialog, Badge, StatePanel), `components/layout/AppShell` (sidebar/header), `features/auth`, `features/dashboard`, `features/clients`, `lib/api` (client et erreurs). Les contrats TypeScript proviennent du schéma DRF via openapi-typescript (`src/lib/api-schema.d.ts`). Les types ne remplacent pas une validation runtime de toute réponse serveur.

Routes : `/connexion`, `/tableau-de-bord`, `/clients`. Router, Query, RHF/Zod et Recharts utilisés. Sessions/CSRF same-origin, aucun credential persistant côté JS. Gardes par capacité explicite ; actualisation des habilitations toutes les 30 secondes et au retour de focus. Le backend décide toujours et réapplique le périmètre. Déconnexion : annuler les requêtes, supprimer les caches privés et mettre à jour le cache d'identité existant (le supprimer rompait la notification de son observer).

Accessibilité : navigation clavier, focus visible et restauré, labels explicites, erreurs associées, titres hiérarchiques, annonces de chargement, tableaux sémantiques, graphiques avec équivalent textuel et contraste vérifié. États chargement/vide/interdit/erreur distincts. Les imports et résolutions présentent un récapitulatif réel avant confirmation.

| Écran | Composants / données | Preuve locale |
|---|---|---|
| Connexion | LoginPage, formulaire vide, CSRF/login, aide administrateur | `screens/connexion.png` vs `01-1.png` |
| Tableau de bord | AppShell, cartes, graphiques, compteur API accessible | `screens/dashboard.png` vs `02-1.png` |
| Panorama Clients | AppShell, recherche/type/pagination serveur, table et fiche minimale | `screens/clients.png` vs `03-1.png` |

Captures sous `.local/ui-review/`. Comparaison visuelle effectuée et corrections de tailles, espacements, sélection de navigation, artwork CSS et labels graphiques. Aucun score de fidélité pixel ni police originale certifiée. Les courbes sont illustratives, leur tracé n'est pas identique au PDF. Captures supplémentaires 768 et 390 px ; absence de débordement horizontal global testée, table défilante. Le responsive est une adaptation, les PDF ne fournissent pas de variante mobile.

Écarts intentionnels : identifiant professionnel (contrat backend username), aucun mot de passe prérempli, connexion persistante/récupération automatique indisponibles. Profil réel de la session, sans identité de collaborateur inventée. Recherche nom/UUID interne, filtre type de personne à la place de profession ; critères métier, création/export et modules futurs désactivés avec explication. Aucun faux statut de synchronisation. Les encours, scores, segments et historiques restent indisponibles en mode API ; aucun calcul métier inventé.

En développement seulement, `?apercu=maquette` et les deux capacités clients.view/clients.view_financial permettent une comparaison illustrée, avec bandeau et footer explicites. Les exemples fictifs statiques du PDF ne sont jamais publiés dans la base, ni utilisés comme règles de scoring. La pagination de cet aperçu annonce huit exemples réels, sans prétendre disposer des 1 248 dossiers de la référence. La condition DEV désactive cet aperçu dans le build production.

Les 13 autres écrans, modules commerciaux, IA, import et intégration Carthago restent hors périmètre. Voir `frontend-phase-status.md` pour les commandes et résultats vérifiés.
