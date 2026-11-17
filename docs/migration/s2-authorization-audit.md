# S2 — autorisation interne, révocation et audit transactionnel

## Périmètre livré

La cible reste quatre services Django/DRF (IAM, Client & CRM, Commercial, Data Integration), une base PostgreSQL avec schémas/credentials propriétaires, et le Gateway M2. **Aucun service métier extrait, aucune table métier déplacée, aucune route publique ajoutée.** S2 fournit et teste les contrats privés avant leur utilisation par un service autonome. Les 38 routes publiques, le code React, les périmètres actuels et le read-only Carthago restent inchangés.

Le backend public continue de faire ses contrôles ORM et de posséder les tables historiques. Les mutations passent maintenant par une admission transactionnelle et une revalidation de l'utilisateur/session après attente. Les verrous Organization existants restent en place. Les nouveaux contrats ne sont inclus que dans `internal_api.urls`, via un listener distinct utilisant `internal_api.settings` ; jamais dans `config.urls`, OpenAPI public ou Nginx.

## Authentification technique et contrats

HMAC-SHA256 versionné sur key-id, audience, timestamp, nonce aléatoire, méthode POST, chemin exact et SHA256 du corps. Fenêtre ±30 secondes ; nonce de 192 bits, digest unique persisté dans `identity_internalnonce`, conservation au moins 65 secondes après réception. Les appels rejoués sont refusés entre processus/listeners, pas seulement dans un cache local. Chaque retry signe un nouveau nonce ; une mutation métier ne doit jamais être rejouée automatiquement.

Clés distinctes par producteur, identifiant et audience ; aucun réemploi de `DJANGO_SECRET_KEY`, de la clé Gateway ou de la clé d'un autre service. Registre `AICED_INTERNAL_KEYS` privé, vide par défaut : tous les appels privés sont alors refusés. La clé détermine le service ; `X-User-ID`, `X-Role`, `actor_id` injecté dans le corps ou une session navigateur sans signature ne confèrent aucun droit. Champs inconnus rejetés, payload borné, comparaison constante. HMAC protège l'intégrité, **pas la confidentialité** : HTTP admis uniquement en loopback par le client ; HTTPS avec validation de certificat requis entre hôtes/conteneurs.

| Endpoint privé (POST) | Audience / autorité |
|---|---|
| `/internal/v1/principal/resolve` | IAM résout la session réelle, utilisateur actif et hash d'auth courant ; aucune délégation par simple UUID. |
| `/internal/v1/authorization/check` | IAM vérifie les capacités demandées dans la même organisation et renvoie scopes/membership UUID minimaux ; pas de données Client. Capabilities autorisées limitées au domaine de la clé ; Integration reçoit seulement du full-organization. |
| `/internal/v1/clients/authorize` | Audience Client, consommateur Commercial seulement ; Client intersecte clients.view, prospects.view si nécessaire, capacité opportunité et droit de lecture sur le même objet. Retour UUID/org/version, jamais de comptes ou données financières. |
| `/internal/v1/audit/events` | Producteur dérivé de la clé, action limitée à son domaine ; reçu append-only dédupliqué par producteur + event UUID. Un contenu contradictoire sous le même ID donne 409. |

La délégation contient la session opaque et le contexte CSRF original (méthode, cookie/token, Origin, Host, scheme). Le contrôleur du service doit les construire depuis la requête reçue, jamais accepter ces paramètres comme choix métier du navigateur. Les mutations sont soumises aux règles Django CSRF ; l'auth technique ne remplace pas l'auth utilisateur. Les lecteurs de session ne flushent ni ne renouvellent la session, pour éviter un verrou exclusif depuis un RPC appelé sous admission partagée.

Le client HTTP ne suit aucune redirection, ne retente pas automatiquement, borne corps/réponse à 64 Kio et utilise un timeout I/O de 3 secondes par défaut. Une indisponibilité, un statut inattendu ou une décision mal formée ferme l'accès (503). Les refus 401/403/404 restent des refus, sans fallback ORM ou principal privilégié. `authorize()` valide actor/org UUID, booléen explicite et forme des scopes/grants. Aucune décision positive n'est mise en cache.

IAM reste responsable des identités/grants, **Client du scoping Client**, Commercial de son lien opportunity/party et Integration de son organisation, policy, double contrôle, quotas et publication. Un grant `assigned` n'est jamais une autorisation d'accès à tous les objets. Les handlers publics historiques continuent ces intersections côté serveur pendant S2.

## Garantie de cohérence et comportement de panne

Le plan S1 proposait une barrière par organisation. S2 choisit une primitive **plus conservative et globale à cette base**, clé versionnée `4711239301896721`, afin de couvrir aussi désactivation utilisateur multi-organisation, changement de mot de passe, rôles globaux et révocation de session :

1. Une mutation métier prend d'abord son verrou Organization historique, puis `pg_advisory_xact_lock_shared` dans sa transaction locale. Elle relit utilisateur/session et droits après attente, puis écrit métier + journal + outbox avant commit.
2. IAM prend le verrou exclusif pour les mutations administratives et logout. Des triggers PostgreSQL imposent aussi le verrou exclusif lors des changements/suppressions User, Organization, Membership, Role, Capability, RoleAssignment, permissions M2M et sessions. Inserts de grants/permissions participent également au protocole.
3. Les lecteurs IAM/Client privés ne prennent pas la barrière : le service appelant la détient jusqu'à son commit. Cela évite un deadlock HTTP avec le demandeur. Les RPC de mutation en cascade ne sont pas autorisés sous cette barrière.
4. Une révocation attend les transactions déjà admises. Son commit précède toute nouvelle admission qui devra alors relire le nouvel état. Un write en attente ne survit pas à une révocation validée ; une révocation ne reçoit pas un faux succès pendant qu'un write admis peut encore commit.

Ce sont des transactions locales, **pas une transaction distribuée**. Aucun lock de table étrangère n'est requis par la primitive d'admission ; les jointures ORM historiques demeurent temporairement pendant S2. Pour un service candidat, `remote_write(authorize, change, audit)` prend admission, appelle l'autorisation fraîche par HTTP, réalise la mutation et exige un callback d'audit local réussi dans cette même transaction. Il ne remplace pas les validations/scopes métier. Un callback d'audit absent/invalide ou en erreur annule le changement.

Crash/rollback ferme l'admission. En cas de panne IAM/Client, aucune nouvelle mutation distante n'est admise ; pas de grants périmés ni de succès optimiste. `lock_timeout` est borné à 5 secondes par défaut dans l'admission et les triggers ; `AUTH_LOCK_TIMEOUT_MS` ajuste l'admission applicative, les triggers gardent leur limite de 5 secondes. Timeout/deadlock/connexion perdue provoque une erreur et rollback : **la révocation n'a pas réussi et doit être réessayée explicitement**, jamais acquittée avant commit. Les transactions/clients bloqués longtemps peuvent donc réduire la disponibilité ; configurer statement/idle-transaction timeouts et supervision avant S3. Ne pas promettre révocation disponible pendant une partition PostgreSQL.

Tous les writers doivent participer. Les triggers IAM couvrent les mises à jour SQL usuelles ; un propriétaire de base/superuser pourrait les désactiver et reste hors du modèle runtime. Ne pas changer de rôle PostgreSQL, session store, cache de grants ou topologie multi-base sans revalider le protocole. Un administrateur faisant du SQL direct contourne l'API d'audit : utiliser les services IAM pour les actions courantes. Le nouveau service Python `deactivate_user` vérifie autorité complète/délégable dans toutes les organisations du sujet, refuse l'auto-désactivation et audite atomiquement ; aucun endpoint admin public supplémentaire.

Les lectures vérifient les droits vivants à chaque appel ; une lecture déjà commencée peut terminer après une révocation concurrente, comme une requête SQL préexistante. Pas de garantie de rappel de données déjà retournées. Les droits expirés, sessions supprimées/expirées, hash de mot de passe modifié et utilisateurs désactivés ne sont pas acceptés par une nouvelle résolution. Aucun token utilisateur durable n'est émis dans S2 : la révocation porte sur sessions et état IAM, pas un JWT prétendument instantanément révoqué.

Les clés techniques relèvent d'un registre de déploiement, pas de cette session utilisateur. Rotation : publier un nouveau key-id/secret, redémarrer les listeners concernés, migrer les clients puis supprimer l'ancien key-id et redémarrer tous les vérificateurs. Pour révocation d'urgence, fermer le listener/réseau concerné avant acquittement opérationnel. Aucune propagation instantanée de changements d'environnement entre processus n'est revendiquée.

## Audit local et livraison

`audit.services.record()` crée AuditEvent et AuditOutbox dans un même `transaction.atomic`. Les mutations IAM/CRM/prospects/activités/imports et login/logout appellent ce code depuis leur transaction métier. Échec de l'insert event **ou** outbox : rollback complet ; aucun événement envoyé en HTTP depuis la transaction métier. AuditEvent et AuditReceipt sont protégés par triggers append-only ; l'identité event/producer/date d'outbox ne peut pas être modifiée ou supprimée par DML. Seuls attempts/delivered_at sont un état de livraison mutable.

La livraison explicite a lieu hors transaction métier, au moins une fois. Crash après acceptation distante mais avant marquage local : replay avec même event UUID et nouveau nonce, reçu unique. Refus/timeout/ack incohérent : outbox reste pending. Pas d'effacement de l'événement ni de suppression automatique des rejets. Le worker traite un batch borné du producteur correspondant à la clé. Les enveloppes excluent **tout context**, donc aucune note, cellule Excel, session, clé ou liste de permissions envoyée au collecteur.

Pendant S2, `/api/audit/` et l'historique des imports lisent toujours l'AuditEvent local existant, immédiatement et avec les mêmes scopes. Les reçus internes ne sont pas injectés en doublon dans cette API. **Avant S3**, adapter la lecture/histoire locale et le contrat central de fraîcheur/pagination ; le simple outbox ne garantit pas une vue centrale immédiate. Les anciens événements ne sont ni réécrits ni automatiquement ajoutés à l'outbox. La politique de rétention/drainage doit être validée avant purge.

## Migrations, démarrage et rollback

Deux migrations additives, sans modification des seize fichiers historiques :

- `identity/0003_internal_authorization` : replay digests et huit triggers IAM/session + fonction de barrière.
- `audit/0004_audit_outbox` : outbox, reçus, unicité producteur/event et protections d'immuabilité.

Aucune table métier déplacée, aucun credential partagé entre nouveaux services car aucun nouveau writer de domaine n'est déployé. Le Gateway/Compose et les routes publiques sont inchangés. Appliquer les migrations **avant de démarrer le nouveau code**, sinon l'audit doit échouer fermé plutôt que laisser des changements sans outbox.

Pour le cluster portable local, le script contrôlé sauvegarde, restaure dans une base scratch marquée, applique les deux migrations au candidat, compare tous les enregistrements et contraintes historiques, vérifie l'absence d'écritures concurrentes, puis applique les deux seules migrations attendues à la base locale :

```sh
python scripts/s2_migrate_local.py --confirm-local-additive
```

Il refuse tout environnement autre que le cluster portable DEBUG/127.0.0.1:55432 ou un plan différent. Le dump contenant les données locales reste privé sous `.local/s2-local-migration/`. Pas de restore automatique sur la base applicative, pas de DROP/RESET, pas de migration de production autorisée. Pour un autre environnement, utiliser la procédure de backup/restore approuvée avant `python manage.py migrate`.

Créer un fichier JSON privé de clés, chaque entrée ayant `secret` (32–128 caractères ASCII URL-safe aléatoires), `service` (`iam`, `client_crm`, `commercial`, `integration`) et `audiences` (`iam`, `client`, `audit`). Ne jamais réutiliser les secrets de la documentation ou des tests. Le registre doit être transmis uniquement aux processus qui en ont besoin ; ne pas l'injecter dans Vite, les logs ou une URL.

```sh
# Listener local privé, même DB historique pendant S2
python scripts/run_internal.py --key-file .local/internal-keys.json --port 8001
# Expirations des nonces, pas de suppression de nonce encore accepté
python scripts/backend_check.py prune_internal_nonces
```

Le worker utilise le même registre via `AICED_INTERNAL_KEYS` dans son environnement :

```powershell
$env:AICED_INTERNAL_KEYS = Get-Content -LiteralPath .local/internal-keys.json -Raw
python scripts/backend_check.py deliver_audit_outbox --endpoint http://127.0.0.1:8001 --key-id client_crm-v1 --limit 100
```

Un registre de développement privé à quatre secrets aléatoires distincts a été créé sous `.local/internal-keys.json`, ignoré par Git ; aucun secret n'est affiché ou documenté. Les key-id locaux sont `iam-v1`, `client_crm-v1`, `commercial-v1`, `integration-v1`. Ne pas les réutiliser en production. Exécuter un batch par producteur configuré ; aucun worker automatique/cron/broker ajouté. Les commandes affichent seulement des compteurs, jamais de payload/secret. Le serveur runserver reste réservé au développement ; aucun déploiement Docker/TLS de production déclaré vérifié.

Rollback : arrêter les consommateurs internes et workers, revenir au code public précédent compatible, conserver **les tables, triggers et événements additifs**. Le backend historique reste l'unique writer ; les verrous Organization et journaux historiques existent toujours. Ne pas faire unapply de la migration outbox après de nouvelles écritures, cela effacerait la trace de livraison. Garder pending/reçus pour reprise et investigation ; ne pas restaurer une ancienne sauvegarde par-dessus des transactions postérieures. Aucun retour de propriété/routage nécessaire en S2.

## Préconditions exactes avant Integration indépendant

1. Entry point/settings/URLConf/image DRF propres, uniquement apps Integration et infrastructure locale nécessaire ; démarrage/restart indépendant prouvé, pas une copie du monolithe chargé dans un deuxième conteneur.
2. Quatre modèles d'import adaptés aux UUID IAM distants, références d'organisation/acteur minimales et validées ; aucune FK ni import de modèles User/Organization/AuditEvent historique dans le runtime candidat. Lignée de migrations propre au schéma Integration, journal/outbox locaux sans FK IAM. Conserver les lignées historiques intactes.
3. Runtime/migrateur/propriétaire du schéma Integration réellement configurés ; tests LOGIN d'échec SELECT/DML/DDL sur IAM/Client/Commercial avec les vraies tables du candidat, pas seulement les probes S1.
4. Brancher **tous** les chemins Integration sur les contrats IAM : context, listes/counts, preview/histoire/rejets CSV, upload/replay, policy/approve/revoke/publish. Exiger imports.view **et** clients.view_financial full-organization, plus capacité d'action, dans la même org. Vérifier CSRF à partir de la requête réelle, jamais d'un choix de payload utilisateur.
5. Remplacer Organization row lock pour quotas/idempotence par une garde locale ; utiliser l'admission commune à la même base puis autorisation HTTP fraîche avant chaque mutation. Lors du packaging S3, sortir la petite primitive `barrier`/`remote_write` de `identity.coordination` dans le socle technique partagé sans imports des modèles session/IAM ; la résolution de session reste dans IAM. Tester le candidat séparé contre révocation IAM réelle, deactivation/password/logout, panne/cancel/timeouts et toutes les anciennes règles de double acteur/idempotence.
6. Journal local + outbox dans la transaction d'import, callbacks audit obligatoires, triggers d'immuabilité et historique local complet ; décision et implémentation de la lecture centrale autorisée/fraîche, monitoring et reprise du backlog. Un reçu technique seul ne remplace pas l'API publique d'audit.
7. TLS/clefs/audiences et réseau privés opérationnels, timeouts PostgreSQL/HTTP et procédures de rotation testés entre vrais processus/credentials ; aucun accès SQL latéral, aucun partage de SECRET_KEY/session DB au candidat. Le premier candidat S3 reste **synthétique, sans trafic public**.
8. Avant cutover actif S4 : backup approuvé/restauré, record counts/PK/contraintes/FK/index/triggers/versions/digests/historique identiques, writer unique (routes **et** jobs/ACL), deltas et rollback post-commit éprouvés. Garder le Gateway sur le backend historique tant que ces critères ne passent pas.

Les adapters Carthago réels, mappings et fusions d'identité/compte restent désactivés. Le manque de mapping ne bloque ni le CRM ni le candidat synthétique, mais interdit toujours les mises à jour autoritaires.

## Vérifications et limites

Exécutions du 14 novembre 2026 :

| Vérification | Résultat |
|---|---|
| Suite backend finale complète | **116/116**, 42,890 s : 104 tests existants + 12 contrats/races S2. Log privé `.local/s2-backend-final.log`. |
| S2 privé sur HTTP réel | **12/12**, 48,549 s dans le run ciblé final, inclus ensuite dans les 116 : headers forgés, signatures/replay/audience/CSRF, scopes objet et org, user/password/session/membership/role/org révoqués, deactivation autorisée, panne audit/outbox, rollback, reçus/digests contradictoires, pannes d'amont et races d'admission. |
| Deux processus Django privés réels | Deux listeners avec même registre/DB : requête signée à session synthétique invalide refusée, replay sur l'autre processus refusé par le nonce partagé, no-store vérifié. Aucun changement métier. Rapport `.local/s2-process-smoke/report.json`. |
| Commandes opérationnelles | Un événement technique IAM livré via le CLI à un listener privé réel : `Audit delivered: 1; pending failures: 0`. Purge : un nonce expiré supprimé, sans purge des nonces actifs. Log privé `.local/s2-delivery-command.log`. |
| Gateway Nginx réel | **10/10**, 79,384 s ; les 38 routes/47 méthodes publiques inchangées, erreurs, spoofing, uploads, sessions, permissions et rollback direct. |
| Chromium via Gateway | **11/11 DEV** (55,6 s), **6/6 bundle compilé** (39,2 s). |
| M1 backup/restore, session restaurée, neuf probes de contraintes | Parité exacte et succès ; deux bases scratch supprimées. |
| Schémas/credentials S1 | Rehearsal réel réussi, quatre schémas/douze rôles ; aucun reste de base/rôle temporaire. Rapport `.local/service-boundaries/682848fe03754e87aea55e3a2ffedc0e/report.json`. |
| Scripts de sécurité | **11/11** tests unitaires. |
| Django check, migration consistency, OpenAPI strict, TypeScript et build Vite | Succès ; `makemigrations --check --dry-run` sans changement supplémentaire. |
| Migration additive locale contrôlée | Dump/restauration exacts avant migration, migration scratch puis locale, conservation des enregistrements et contraintes historiques ; trois nouvelles tables seulement. Rapport `.local/s2-local-migration/815375c5728a488986f067acfa57a3f1/report.json`. |

Rapport complet M1/M2 : `.local/migration-baseline/336023431c624ab78a4e5bde117a1fe6/report.json`, `passed`, empreintes applicatives avant/après identiques et scratch supprimé. Ce gate avait exécuté les 114 tests alors présents ; après les deux assertions/scénarios S2 supplémentaires et le callback d'audit obligatoire, la suite complète finale **116 tests** ci-dessus a été réexécutée. Les changements supplémentaires concernent les contrats privés, sans modification des pages ou routes publiques.

Échecs préliminaires explicitement conservés : le premier gate (`e28c859fcaa845c084ddb655117d921f`) a passé le backend mais échoué au navigateur, car la colonne producer d'outbox a été ajoutée pendant qu'il utilisait un scratch déjà migré. Le gate corrigé repart de migrations fraîches ; les deux scratch du run échoué ont été supprimés et la base applicative était inchangée. Le premier préflight local a refusé de migrer l'application parce que Django ajoute trois content types et douze permissions de modèles ; le contrôle a été corrigé pour autoriser **uniquement** ces ajouts attendus tout en conservant chaque ancienne ligne. Ces permissions Django ne sont pas des habilitations métier et n'accordent aucun accès financier/IT.

La base locale a ensuite reçu les deux migrations, donc le schéma n'est plus identique à celui d'avant S2 : l'inventaire actualisé est **33 tables, 28 modèles, 18 migrations applicatives, 38 routes**. Les données métier et anciens enregistrements sont préservés ; les probes privés ajoutent seulement des nonces et des événements techniques de refus auditables. Aucune donnée de production migrée et aucune table métier déplacée.

Limites : aucun build/run Docker ou TLS de production sur cette machine ; pas encore de candidat Integration ni de migrations propriétaires par service. Le test de panne HTTP couvre connexion refusée et réponse invalide ; pas de test de failover PostgreSQL, de partition prolongée ni de système HA. Le délai HTTP est un timeout d'I/O, pas une limite totale contre un serveur qui émet indéfiniment au compte-gouttes ; configurer des deadlines d'exploitation et timeouts de transaction avant S3. Une transaction admise bloquée peut faire échouer la révocation par timeout, mais ne permet pas de l'acquitter à tort. La lecture centrale des futurs événements distants et les vrais credentials/TLS/ACL Integration restent les gates explicites de la section précédente.

## Fichiers modifiés

- `backend/internal_api/{security,client,views,urls,settings,tests}.py` et `scripts/run_internal.py` : contrats privés signés, listener séparé, client et tests HTTP.
- `backend/identity/{coordination,services,authentication,models}.py`, migration `identity/0003_internal_authorization.py` ; callers dans `clients/{services,workspace,prospects}.py` et `ingestion/services.py` : admission/révocation et revalidation après attente.
- `backend/audit/{models,services,delivery}.py`, migration `audit/0004_audit_outbox.py` : audit/outbox local et reçus append-only.
- `backend/core/management/commands/{deliver_audit_outbox,prune_internal_nonces}.py` : commandes bornées de livraison et maintenance technique ; `core/middleware.py` : no-store aussi sur les réponses privées.
- `backend/config/settings.py`, `.env.legacy.example` : clés techniques séparées et timeout d'admission ; aucune clé réelle versionnée.
- `scripts/{migration_baseline,s2_migrate_local}.py`, `backend/service_architecture/ownership.py`, `docs/migration/service-inventory.json` : gate S2, backup/migration locale contrôlée et inventaire propriétaire actualisé.
- README, architecture/roadmap, plan S1 et ce bilan : statut, garanties, procédures et prérequis S3. Aucun source React, URLConf public, fichier Nginx/Compose ou migration historique modifié.
