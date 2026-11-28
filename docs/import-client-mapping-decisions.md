# Décisions utilisateur : mapping des imports vers les clients

Ces décisions cadrent la synchronisation des lots publiés. Les personnes
physiques et morales opérationnelles utilisent des identifiants source séparés
et une synchronisation en arrière-plan après publication revue. La projection
synthétique reste limitée à sa base de démonstration.

- Personnes physiques : la colonne B est l'identifiant source stable ; l'UUID
  interne AICED reste distinct.
- Personnes morales : la colonne B est l'identifiant source stable, dans un
  espace distinct de celui des personnes physiques.
- Comptes : la colonne D contient l'identifiant de la colonne B de la personne.
  Un détenteur absent ou ambigu doit être soumis à revue, sans rapprochement par
  nom. Cette décision ne confirme pas un lien avec une personne morale.
- Contacts : les valeurs importées renseignées remplacent les valeurs CRM
  correspondantes. Une cellule vide conserve la valeur CRM existante. Le CRM
  ne possède qu'un champ téléphone : le téléphone source est prioritaire, le
  mobile est utilisé à défaut.
- Visibilité : noms, dates de naissance et coordonnées sont accessibles aux
  utilisateurs autorisés à consulter le dossier, dans leur périmètre habituel.
  Aucun droit inter-organisation ou financier n'est accordé implicitement.

La publication doit conserver staging, validation, revue, historique et
provenance. Les reprises doivent être idempotentes et les données source plus
anciennes ne doivent pas écraser une situation plus récente. L'absence d'une
ligne dans un export ne supprime aucun client. Les identités existantes ne sont
pas fusionnées sur la base du nom.

À concevoir avant activation : registre de liens et résolution des conflits,
droits sur chaque objet créé, ordre et attribution des dossiers importés,
traitement des doublons et erreurs, synchro transactionnelle et relançable,
exposition contrôlée de la date de naissance et tests d'isolation. Le modèle
actuel n'a pas de champ de naissance dans PhysicalPerson. Les données de compte
restent séparées des champs CRM et soumises aux droits financiers existants.

## Projection opérationnelle

`clients.operational_imports.apply_physical_page` conserve une projection par
organisation et identifiant B, avec UUID client distinct et provenance du lot,
de la ligne et de la date. La page est atomique ; les replays et observations
plus anciennes sont ignorés. Les tests ciblés couvrent l'isolation organisation,
la visibilité du dossier, les contacts vides, la validation et le rollback.
Un worker dédié lit des pages bornées via Integration, limitées aux snapshots
opérationnels publiés avec configuration fixe v1. Il vérifie organisation,
lot et type, reprend au curseur sauvegardé et affiche son état après contrôle
des habilitations d'import. Les sociétés utilisent une projection distincte.
Les comptes sont liés uniquement à une personne physique dont l'identifiant B
correspond à la colonne D, dans la même organisation. Un détenteur introuvable ou
changé bloque la page ; une nouvelle tentative est prévue. Les comptes sont
visibles aux utilisateurs autorisés à voir à la fois le dossier et ses données
financières. Aucun solde ni valorisation n'est déduit du fichier.

La validation isolée comprend les tests PostgreSQL d'identité, rejouabilité,
atomicité et isolation et deux scénarios Chromium avec trois classeurs
synthétiques : dépôt, revue distincte, publication, suivi du traitement,
affichage des clients, du compteur et du compte. Aucun classeur client réel
n'a été importé par ces tests. Les lots historiques non classifiés et les
rapprochements avec des clients AICED existants ne sont pas synchronisés.
