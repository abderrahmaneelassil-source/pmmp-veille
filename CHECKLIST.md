# Checklist de vérification du collecteur PMMP — 25/09/2026 (après-midi)

Branche `checklist-2026-09-25`, créée depuis `passation-2026-09-25` @ `ceae906`.
**Aucun push, aucun merge.** Tous les crawls de cette vérification ont visé le
**faux portail local** (127.0.0.1). Le vrai site n'a **jamais** été contacté.

Méthode : la checklist transmise a été appliquée point par point à ce projet.
Pour chaque point : statut réel, preuve ou correction, et pour les manques
restants, la raison. Les preuves datées du 24/09 renvoient à `AUDIT.md` ; tout ce
qui est marqué « vérifié le 25/09 » a été **refait aujourd'hui**.

Deux environnements ont été utilisés :

- **La vraie base `pmmp_veille`**, avec le compte `pmmp_app` du `.env`. Lecture
  seule, sauf les contrôles de droits, faits dans des transactions annulées.
- **Une base PostgreSQL 18 jetable** (cluster temporaire, port 5499, supprimé
  après usage), pour lancer les tests PostgreSQL et les runs consécutifs sans
  toucher à `pmmp_veille` ni au mot de passe `postgres`.

## Résumé

| # | Point | Statut |
|---|---|---|
| 1 | Fonctionnement métier | ✅ OK sur faux portail et pages réelles capturées · ⚠️ jamais exécuté sur le vrai portail au-delà de la page 1 |
| 2 | Gestion des erreurs | ✅ OK · **corrigé** : messages d'échec illisibles |
| 3 | Sécurité | ✅ OK · ⚠️ dépôt GitHub **public** |
| 4 | Configuration | ✅ OK · **corrigé** : taille de lot par défaut (2000 → 1200) |
| 5 | Dépendances | ✅ OK · **corrigé** : `pyproject.toml` sans dépendances, test incompatible 3.11 |
| 6 | Tests | ✅ 109 tests verts · **ajouté** : liste vide · ❌ restent : gros volume, perte de la base en cours de run |
| 7 | Automatisation | **corrigé** : double instance, runs morts · ❓ week-end à trancher |
| 8 | Fichiers produits | ✅ pas d'écrasement, pas de retéléchargement · ❌ DCE rectifié jamais repris |
| 9 | Logs et traçabilité | ⚠️ partiel : statuts en français, compteurs d'erreurs dans le JSON `stats` |
| 10 | Notifications | ❌ **aucune** : manque confirmé |
| 11 | Performance | ✅ mesurée : 45 s par run plafonné (faux portail, délai réel de 3 s) |
| 12 | Idempotence | ✅ base et DCE · ⚠️ HTML brut des pages de liste réécrit à chaque run |
| 13 | Plan de reprise | ✅ documenté · ❌ **aucune sauvegarde automatique de la base** |
| 14 | Documentation | ✅ PASSATION.md complétée, responsable indiqué |
| DB | Base `pmmp_veille` réelle | ✅ schéma conforme, 14/14 droits · **vide : aucun run n'a encore eu lieu** |

Commits de cette vérification :

| Commit | Point | Contenu |
|---|---|---|
| `d8a14a6` | 7 | Un seul run à la fois (verrou système, code de sortie 4) |
| `8586e0e` | 7 | Runs interrompus détectés au lieu de rester `en_cours` |
| `3a6fc58` | 4 | Taille de lot par défaut alignée sur 1200 (`.env.example`, code, README) |
| `a6b74b9` | 5 | Dépendances déclarées dans `pyproject.toml`, tests compatibles Python 3.11 |
| `52ea4dd` | 6 | Test : page de résultats vide |
| `4db5f5e` | 2 | Cause d'échec lisible dans les logs (code HTTP, délai dépassé) |
| `4d7232b` | 13-14 | PASSATION.md : exploitation, rollback, sauvegarde, responsable |
| `8e7baea` | — | DEMO.md : mis à jour (branche, nombre de tests) |

**Aucune modification du schéma de la base ni de `db/roles.sql`.** Les deux
ajouts du point 7 n'en ont pas besoin : l'un est un verrou fichier, l'autre utilise
un `UPDATE` sur `collecte_runs`, déjà autorisé à `pmmp_app`. C'est volontaire :
modifier le schéma de `pmmp_veille` demande le superutilisateur, qui n'était pas
disponible aujourd'hui.

---

## 1. Fonctionnement métier — ✅ (avec une réserve)

| Question | Réponse | Preuve |
|---|---|---|
| Liste, pagination, fiche détail, DCE, historique : fait-il ce qui est prévu ? | Oui, sur le faux portail et sur les pages réelles capturées le 23/09. | `test_nominal_crawl_respects_collection_rules` (liste → 100 résultats par page → 6 fiches → 6 DCE) ; pagination PRADO : `test_listing_yields_prado_postback_and_defers_details`, `test_pagination_stops_if_page_repeats` ; historique : `test_history.py`, `test_two_crawls_with_database` |
| Scénarios principaux (suite relancée le 25/09) | **109 tests, tous verts** : 102 sans base (+ 7 ignorés) ; **109/109 avec la base jetable**, y compris les tests PostgreSQL non vérifiés ce matin (reprise de bout en bout comprise). | `pytest` relancé deux fois (voir §6) |
| Cas particuliers dans `test_robustness.py` | Toujours vrai : 14 tests verts (13 existants + 1 ajouté aujourd'hui). Page de liste inattendue, fiche 404 / timeout, DCE absent, DCE en 404 / timeout, dates invalides. « DCE au mauvais format » : une page HTML à la place du fichier est détectée et archivée sans être soumise (`test_dce_intermediate_page_is_never_submitted`). Doublons : upsert (`test_upsert_no_duplicates_and_history`). **Ajouté** : liste de résultats vide (`test_empty_results_page_is_logged_and_run_is_not_a_success`). | `tests/test_robustness.py` |
| Cycle complet sur `fixtures/live/` | Rejoué le 25/09 : `test_full_cycle_on_live_fixtures` **passe** (5 vraies consultations ; insertion, rejeu sans doublon, rejeu modifié → historique `report_date`, `rectificatif`, `annulation`, `resultat`). | Base jetable, 25/09 |

**Réserve :** la pagination au-delà de la page 1 n'a **jamais** tourné contre le
vrai portail. La capture du 23/09 ne contient qu'une page, et le faux portail
n'en a qu'une aussi. La logique multi-pages n'est testée qu'en unitaire. Le
premier vrai test sera le run du 26/09 à 06:00.

## 2. Gestion des erreurs — ✅ (corrigé)

- **Arrêt propre sur échec** : revérifié le 25/09 par un vrai crawl contre un faux
  portail qui répond HTTP 503. Arrêt après 3 erreurs (`CIRCUIT BREAKER DÉCLENCHÉ`),
  code de sortie 1, statut `echec`, raison enregistrée. Test
  `test_circuit_breaker_stops_real_crawl` vert.
- **Lisibilité des messages** : le log d'un run en échec a été relu comme le lirait
  quelqu'un qui ne connaît pas le code. Les messages sont en français et donnent
  l'URL, un compteur (« Problème 2/3 ») et la raison de l'arrêt. **Deux causes
  étaient illisibles, corrigées (`4db5f5e`)** :
  `HttpError('Ignoring non-200 response')` (sans le code HTTP) devient
  « réponse HTTP 503 », et `TimeoutError('')` devient « délai dépassé : le portail
  n'a pas répondu à temps (PMMP_DOWNLOAD_TIMEOUT) ».
- **Enregistrement des erreurs** : chaque erreur est dans le log
  (`storage/logs/run_*.log` via la tâche planifiée), comptée dans
  `collecte_runs.stats`, et la raison d'arrêt est dans `collecte_runs.raison`.
  **Limite :** les refus **avant** démarrage (hors fenêtre, base injoignable, run
  déjà en cours) ne créent **aucune** ligne dans `collecte_runs`, seulement le
  message dans le log et le code de sortie. Le refus de 11:46 aujourd'hui n'est
  donc pas en base.
- **Reprise sans recommencer de zéro** : le mécanisme évoqué lors du passage au
  matin **est bien implémenté**. Il ne mémorise pas de numéro de page : c'est la
  base qui sert de point de reprise (AUDIT.md, « Reprise de pagination »).
  **Testé pour de vrai le 25/09** avec 5 runs consécutifs plafonnés (`--force`,
  lot de 4, mode prod), sur le faux portail et la base jetable :

  | Run | Fiches visitées | Requêtes | Consultations en base | DCE sur disque |
  |---|---|---|---|---|
  | 1 (base vide) | 1000, 1001, 1002, 1003 | 11 | 4 | 4 |
  | 2 (reprise) | 1004, 1005 | 7 | 6 | 6 |
  | 3 (tout à jour) | aucune | 3 | 6 | 6 |
  | 4 (rejeu identique) | aucune | 3 | 6 | 6 |
  | 5 (date limite de 1002 reportée) | 1002 seulement | 4 | 6 (+2 lignes d'historique, `run_id` = 5) | 6 (DCE `deja_present`) |

  Le test automatique `test_incremental_batches_resume_night_after_night` (4 runs
  réels + PostgreSQL) passe aussi.

## 3. Sécurité — ✅ (une réserve)

- **Mots de passe / tokens (revérifié le 25/09)** : le mot de passe réel de
  `pmmp_app` (32 caractères) apparaît **0 fois** dans les fichiers suivis et
  **0 fois** dans tout l'historique (`git log --all -p`). Recherche par motifs
  (URL avec mot de passe, `password=`, clés privées, AWS, GitHub, `api_key` /
  `secret` / `token`) : une seule occurrence, le modèle
  `postgresql://postgres:MOT_DE_PASSE_POSTGRES@` de la documentation.
- **Fichiers sensibles exclus** : `git check-ignore -v` confirme `.env`,
  `storage/*` (dont `last_run.json`, `dce/`, `raw_html/`, `logs/` et le nouveau
  `storage/.crawl.lock`), `.venv/` et `.idea/`. Seuls les 3 `.gitkeep` de
  `storage/` sont suivis. Aucun serveur web ne sert ces dossiers : ils restent sur
  le disque local.
- **Droits de `pmmp_app`** : **14/14 contrôles conformes le 25/09**, avec la même
  liste que le 24/09 (voir « Vérification directe de la base »).
- ⚠️ **Nouveau constat : le dépôt GitHub `abderrahmaneelassil-source/pmmp-veille`
  est public** (l'API GitHub répond 200 sans authentification). Il ne contient
  aucun secret, mais il est lisible par tous : documentation d'infrastructure
  (noms de comptes, retrait des droits `PUBLIC`), pages capturées du portail.
  **Non modifié** : c'est au propriétaire du dépôt de décider.

## 4. Configuration — ✅ (corrigé)

- **Chemin personnel en dur** (`C:\Users\<nom>\…`) : `git grep` sur tout le dépôt,
  plus l'historique. **Aucun dans le code** (`src/`, `scripts/`, `db/`, `tests/`).
  - `scripts/run_nightly.ps1` part de `$PSScriptRoot`, `run_nightly.sh` de
    `BASH_SOURCE`, et `db.py` localise `schema.sql` par rapport à son propre
    fichier : rien ne dépend du nom d'utilisateur.
  - Le chemin `C:\Users\abder_r9rl0a3\pmmp_collector` apparaît uniquement dans la
    **documentation** (DEMO.md, PASSATION.md : c'est l'emplacement réel sur ce PC)
    et dans la **tâche planifiée Windows**, qui est hors Git. Rien à corriger dans
    le code.
- **Chemins, adresses, URLs, noms de fichiers** : tout vient de `.env`. L'URL du
  portail, la base, l'User-Agent, la fenêtre, le fuseau et les dossiers de
  stockage passent par `config.py`, dont les valeurs par défaut sont documentées.
  Les seuls noms fixes sont internes au dossier de stockage (`last_run.json`,
  `raw_html/`, `dce/`…).
- **Corrigé (`3a6fc58`)** : `.env.example`, la valeur par défaut de `config.py` et
  le README indiquaient encore `PMMP_MAX_ITEMS=2000`. Une nouvelle installation
  aurait donc repris 2000 et fini en `partiel`. Ils sont alignés sur 1200, la
  valeur du `.env` réel.
- **Sur un autre PC ou serveur**, obstacles relevés (non bloquants pour le code) :
  1. la tâche planifiée est liée au compte Windows `abder_r9rl0a3`, session
     ouverte : il faut la recréer (commande en tête de `run_nightly.ps1`) ;
  2. la base locale utilise la collation `English_United States.1252` (sous
     Linux, créer la base en UTF-8) ;
  3. `run_nightly.sh` n'a jamais été exécuté (seule sa syntaxe a été vérifiée) ;
  4. `db/roles.sql` retire le droit `CONNECT` à `PUBLIC` sur les **autres bases**
     du serveur (à prévoir sur un serveur partagé) ;
  5. la commande de sauvegarde de PASSATION.md cite le chemin d'installation
     Windows de PostgreSQL 18.

## 5. Dépendances — ✅ (corrigé)

- **Recherche automatique des imports** (analyse `ast` de `src/` et `tests/`).
  Paquets tiers importés : `scrapy`, `parsel`, `pydantic`, `psycopg`, `dotenv`,
  `pytest`, `twisted` (tests), plus `tzdata`, utilisé indirectement par
  `zoneinfo`. Tous sont installés et couverts par `requirements.txt`. `parsel`
  (importé directement par `parsers.py`) et `twisted` n'y étaient que via Scrapy :
  `parsel` a été ajouté explicitement (aucune nouvelle dépendance).
- **Corrigé (`a6b74b9`)** :
  - `pyproject.toml` ne déclarait **aucune** dépendance : `pip install .` seul
    donnait un paquet inutilisable. Elles sont maintenant déclarées, avec les
    mêmes contraintes que `requirements.txt`.
  - `tests/test_crawl_integration.py` contenait un antislash dans une f-string :
    **SyntaxError sous Python 3.11**, alors que le projet annonce `>= 3.11`.
    Corrigé.
- **Version de Python** : **3.14.5**, le seul interpréteur installé sur ce PC.
  Elle est documentée : README §2 (« Python 3.11 ou plus, testé avec 3.14 ») et
  `pyproject.toml` (`requires-python = ">=3.11"`). **Limite :** la compatibilité
  3.11 a été vérifiée par analyse de la syntaxe, pas en exécutant les tests
  sous 3.11.

## 6. Tests — ✅ (deux trous restants)

**Résultat au 25/09 :** 102 passed + 7 skipped sans base ; **109 passed** avec
`PMMP_TEST_DATABASE_URL` pointant vers la base jetable.

| Cas | Couvert ? | Où |
|---|---|---|
| Données normales | ✅ | `test_nominal_crawl…`, `test_live_fixtures.py`, cycle complet |
| Aucune donnée | ✅ (liste vide **ajoutée le 25/09**) | `test_empty_results_page…`, `test_listing_unexpected_html…` |
| Donnée incorrecte | ✅ | `test_bad_deadline_drops_only_that_item` (5 variantes), `test_models.py` |
| Perte de connexion / portail indisponible (timeout) | ✅ | timeouts liste / fiche / DCE, HTTP 404/500/503, circuit breaker, 403/429 |
| Base injoignable au démarrage | ✅ | `test_unusable_database_fails_fast…` |
| PC qui redémarre pendant un run | ✅ (**ajouté le 25/09**) | `test_lock_is_released_when_holder_is_killed`, `test_stale_running_run_is_marked_dead`, `test_crawl_marks_dead_run_before_starting` |
| **Beaucoup de données** | ❌ | Aucun test de volume : le faux portail a 6 consultations sur 1 page. Seuls les plafonds (`test_max_items`) sont testés. Or le vrai portail compte ≈ 100 000 consultations sur ≈ 1 000 pages à 100 par page. |
| **Perte de la base en cours de run** | ❌ | La reconnexion de `PostgresPipeline` (`pipelines.py`, branche `if self.conn.closed`) n'est couverte par aucun test. |
| DCE corrompu (archive invalide) | ❌ (non vérifié par le code) | Le contenu du DCE n'est pas validé : un fichier corrompu est enregistré tel quel. |

- **Lancement manuel `--force`** : testé (`test_nominal_crawl…`,
  `test_circuit_breaker…`, `test_two_crawls_with_database`…).
- **Lancement automatique dans la fenêtre, sans `--force`** : testé
  (`test_accepted_inside_window_without_force`, et le premier run de
  `test_second_crawl_refused_while_first_is_running`).
- Ce qu'aucun test ne couvre : le **déclenchement par le Planificateur à 06:00**
  (voir §7).

## 7. Automatisation

### Deux exécutions simultanées — **corrigé (`d8a14a6`)**

Avant, sous Windows, rien ne l'empêchait : `MultipleInstances = IgnoreNew`
protège seulement la tâche contre elle-même, pas un lancement manuel en parallèle.
Sous Linux, `flock` dans `run_nightly.sh` protégeait déjà.

- `crawl` prend désormais un **verrou du système** sur `storage/.crawl.lock`
  (`msvcrt` / `fcntl`, bibliothèque standard, aucune dépendance). Un second run
  est **refusé avec le code 4**, sans aucune requête. Le message indique le PID
  du run en cours.
- J'ai choisi un verrou fichier plutôt que de chercher un run `en_cours` en base :
  le verrou est libéré **par le système** quand le processus meurt (kill,
  redémarrage), donc il ne peut jamais rester bloqué. La vérification en base
  aurait été mise en échec précisément par les lignes `en_cours` fantômes.
- Tests : `test_second_process_is_refused_while_lock_is_held`,
  `test_lock_is_released_when_holder_is_killed` et
  `test_second_crawl_refused_while_first_is_running`. Ce dernier lance un vrai
  crawl dans la fenêtre ; pendant qu'il tourne, le second `crawl --force` est
  refusé (code 4). Le faux portail ne reçoit que les 15 requêtes du premier run.
- Scripts `run_nightly.ps1` / `.sh` et README (codes de sortie) mis à jour.

### Redémarrage du PC pendant un run — **corrigé (`8586e0e`)**

- Au démarrage, une fois le verrou pris, `crawl` passe en `echec` tout run
  `en_cours` depuis plus de `PMMP_STALE_RUN_HOURS` (**6 h** par défaut), avec la
  raison `interrompu : resté en_cours plus de 6 h (processus disparu : arrêt du
  PC, kill…), détecté le …`. Il l'écrit aussi dans le log (`ATTENTION : le run
  n°…`). `termine_le` reste vide : l'heure réelle de l'arrêt n'est pas connue, et
  elle n'est pas inventée.
- **Pourquoi 6 h et pas « la durée d'un crawl plafonné »** : un run plafonné
  (`--force`) dure environ 1 min, mais un run planifié normal dure légitimement
  jusqu'à **4 h** (fenêtre 06:00–10:00), et la tâche est coupée à **5 h**. Un seuil
  plus court ferait déclarer mort un run bien vivant.
- Tests PostgreSQL : `test_stale_running_run_is_marked_dead` (run ancien → échec,
  run récent et run terminé intacts, opération idempotente) et
  `test_crawl_marks_dead_run_before_starting` (vrai crawl). Droit vérifié sur la
  vraie base : l'`UPDATE` passe avec `pmmp_app`, en transaction annulée.
- **Limite :** pendant les 6 premières heures, un run tué reste affiché
  `en_cours`.

### Fuseau horaire — ✅ revérifié le 25/09

| Élément | Valeur |
|---|---|
| Windows | `Morocco Standard Time`, UTC+00:00 |
| `tzdata` | 2026.4 (IANA 2026d) : `Africa/Casablanca` = +00:00 à 15:41 |
| Session PostgreSQL | `TimeZone = Africa/Casablanca` |
| Réglage de la base | `TimeZone=Africa/Casablanca` |
| Déclencheur de la tâche | `2026-09-26T06:00:00+00:00` |

Tout est cohérent, et les tests de fenêtre (`test_default_window_is_morning`…)
passent.

### Week-ends et jours fériés — ❓ question ouverte, non tranchée

Aujourd'hui, la tâche tourne **tous les jours**, week-end et jours fériés compris
(déclencheur `Daily`), et le code ne distingue aucun jour. Faut-il collecter le
week-end ? Le portail publie peu ces jours-là, mais les dates limites courent
quand même. **À décider par le chef de projet**, rien n'a été changé.

## 8. Données et fichiers produits

- **Collision de noms de DCE**
  - Dans le dossier d'une consultation : **aucun écrasement**. `DceStore.save`
    ajoute `_1`, `_2`… si le nom existe déjà, et écrit via un fichier `.part`
    renommé ensuite.
  - Entre deux consultations, le dossier s'appelle `<org>__<ref>`, nettoyé par
    `safe_name`. Deux clés qui ne diffèrent que par des caractères spéciaux
    (`A/B` et `A_B`) auraient le même dossier. **Collision théorique seulement** :
    les vraies clés sont alphanumériques (`q9t`, `1038578`). Non corrigé : ça
    aurait changé la règle de nommage le jour de la démo.
  - Constaté sur les runs du 25/09 : 6 consultations → 6 dossiers distincts
    `t1__1000/DCE.zip` … `t1__1005/DCE.zip`.
- **DCE déjà téléchargé** : **pas retéléchargé, pas écrasé**. Run 5 : fiche 1002
  revisitée, DCE `deja_present`, 0 requête DCE, toujours 6 fichiers.
- ❌ **Manque métier** : pour la même raison, **un DCE rectifié sur le portail
  n'est jamais retéléchargé**. Dès qu'un fichier existe dans le dossier, la
  consultation est `deja_present`. Idem si un seul des 2 liens DCE a réussi : le
  second ne sera jamais retenté. **Pas corrigé** : il faut d'abord décider quand
  retélécharger (à chaque rectificatif ? garder les versions ?).

## 9. Logs et traçabilité — ⚠️ partiel

Contenu réel de `collecte_runs`, champ par champ :

| Attendu | Présent ? | Colonne |
|---|---|---|
| Heure de début | ✅ | `demarre_le` (timestamptz) |
| Heure de fin | ✅ | `termine_le` (vide si le run a été tué) |
| Nombre d'éléments traités | ⚠️ pas en colonne | `stats->>'pmmp/listing_rows'` (JSON) |
| Réussis | ✅ | `nb_consultations` (enregistrées en base) |
| En erreur | ⚠️ partiel | `nb_ecartees` = rejetées par la validation seulement ; fiches, DCE et base en erreur : `stats->>'pmmp/detail_errors'`, `'pmmp/dce_errors'`, `'pmmp/db_errors'` (JSON) |
| Message d'erreur | ⚠️ court | `raison` : code (`circuit_breaker`, `aucune_consultation_extraite`…) ou détail du circuit breaker ; le message complet de chaque erreur est seulement dans le log |
| Statut final clair | ⚠️ pas les mots demandés | voir ci-dessous |

**Les statuts ne sont pas SUCCESS / WARNING / FAILED.** Ce sont des mots
français, fixés par une contrainte `CHECK` du schéma. **Rien n'a été renommé.**
Correspondance proposée :

| Statut actuel | Équivalent | Code de sortie | Sens |
|---|---|---|---|
| `succes` | **SUCCESS** | 0 | Run terminé, au moins une consultation lue |
| `partiel` | **WARNING** | 3 | Fenêtre fermée à 10:00 avant la fin : données partielles enregistrées |
| `echec` | **FAILED** | 1 | Circuit breaker, captcha, aucune consultation extraite, erreurs base, ou run interrompu (nouveau) |
| `refuse` | (FAILED sans effet) | 2 | Rare en base : les refus sont presque toujours faits avant l'écriture en base |
| `en_cours` | — | — | Pas un statut final |

Renommer (ou ajouter des colonnes de compteurs) demande de modifier le schéma
avec le superutilisateur, et de mettre à jour la vue `v_dernier_run_reussi` :
**à décider**.

## 10. Notifications — ❌ manquant (confirmé)

Aucun mécanisme d'alerte : `git grep` de smtp, mail, webhook, slack, teams,
notify et alert dans `src/`, `scripts/` et `db/` ne donne rien. Il existe
seulement la vue SQL `v_dernier_run_reussi` (README §8 : « alerter si plus de
26 h »), mais **rien ne l'interroge**.

**Pourquoi ça compte :** si la collecte échoue (portail modifié, circuit breaker,
PC éteint, session fermée), personne n'est prévenu. La panne peut durer des jours
sans être vue, et les appels d'offres de cette période sont manqués. C'est le
manque le plus important pour l'exploitation. **Non improvisé aujourd'hui**, noté
dans PASSATION.md, « Ce qui reste à faire ».

## 11. Performance

Mesures du 25/09, sur le faux portail local :

| Run | Réglages | Durée | Requêtes |
|---|---|---|---|
| Plafonné `--force`, base vide | **délai réel de 3 s**, plafonds réels (1 page, 10 fiches), 6 consultations | **45,2 s** (collecte_runs : 42 s) | 15 |
| Même run rejoué (tout à jour) | idem | **9,1 s** (collecte_runs : 6 s) | 3 |
| Run plafonné, délai de test 1 s | lot de 4 | 13,3 s | 11 |

- Estimation (non mesurée) sur le vrai portail pour `--force` : 10 fiches + 10 DCE
  + 4 requêtes de liste ≈ 24 requêtes à ≥ 3 s, soit **≈ 1 min 15 plus la latence
  du portail**.
- **Aucune boucle inutile** : une page de liste identique à la précédente arrête
  la pagination (`test_pagination_stops_if_page_repeats`). Aucune nouvelle
  tentative automatique (`RETRY_ENABLED = False`).
- **Aucun retéléchargement** de fiches ni de DCE déjà en base et inchangés : runs
  3 et 4 = 3 requêtes (robots.txt, liste, choix de 100 par page), 0 fiche, 0 DCE.
- En revanche, les **pages de liste sont relues à chaque run**. C'est nécessaire
  pour détecter les nouveautés. Une fois la base remplie, cela fait ≈ 1 000 pages
  de liste chaque matin (≈ 50 min à 3 s).

## 12. Idempotence — ✅ base et DCE · ⚠️ HTML brut

Même run relancé (runs 3 et 4 ci-dessus, puis le rejeu du §11) :

- **Base** : aucun doublon (clé naturelle unique, 0 doublon mesuré), aucune ligne
  d'historique parasite, une ligne `collecte_runs` par run.
- **DCE** : **pas retéléchargés, pas réécrits** (6 fichiers, inchangés).
- **HTML brut : oui, réécrit à l'identique à chaque run.** Chaque run crée un
  nouveau dossier `storage/raw_html/<horodatage>/` et y réarchive les pages de
  liste lues, même inchangées (+1 fichier par run sur le faux portail, contenu
  identique au run précédent), plus une ligne dans `index.jsonl`. **Ce n'est pas
  bloquant, mais rien ne purge ces fichiers.** Ordre de grandeur (estimation) :
  une vraie page de liste à 10 résultats pèse 303 Ko. À 100 résultats par page et
  ≈ 1 000 pages par matin, on peut atteindre **plusieurs centaines de Mo, voire
  plus d'1 Go, par jour**. Il faut décider d'une durée de conservation (manque
  noté dans PASSATION.md).

## 13. Plan de reprise — ✅ documenté · ❌ pas de sauvegarde

Ajouté dans PASSATION.md, section « Exploitation » (`4d7232b`) :

- **Arrêter** : `Disable-ScheduledTask` / `Stop-ScheduledTask`, Ctrl+C ou
  `Stop-Process` (avec la commande pour retrouver le processus). Non vérifié :
  si `Stop-ScheduledTask` arrête aussi le `python.exe` enfant. La procédure
  demande donc de le contrôler.
- **Relancer** : `Enable-ScheduledTask`, `crawl --force`, `Start-ScheduledTask`.
- **Revenir à un commit précédent** : `git revert` (à préférer) ou
  `git switch --detach`, puis `pip install -r requirements.txt` et `pytest`.
- **Sauvegarde de la base : il n'en existe aucune**, ni tâche ni fichier (vérifié
  le 25/09 : les tâches « Backup » présentes sont des tâches système de Windows).
  **C'est un vrai manque.** La commande `pg_dump` (avec `pmmp_app`) /
  `pg_restore` écrite dans PASSATION.md a été **testée** aujourd'hui : dump de
  `pmmp_veille` réussi (code 0), puis restauration réussie des 3 tables dans une
  base jetable. Il reste à la **planifier** et à copier les fichiers hors du PC.

## 14. Documentation — ✅

PASSATION.md couvre maintenant :

| Sujet | Où |
|---|---|
| Objectif | « En deux minutes » |
| Fonctionnement général | « En deux minutes », décisions 2–3 |
| Emplacement du code | « Où trouver quoi » (ajouté) |
| Configuration | décision 1, `.env` |
| Dépendances | « Où trouver quoi » (ajouté) |
| Lancement / arrêt | « Exploitation » (ajouté) |
| Erreurs fréquentes | « Exploitation » (ajouté), plus README §4 |

**Personne responsable** (ajouté en tête) : Abderrahmane Elassil (stagiaire),
jusqu'au 25/09/2026. **Après cette date, l'équipe doit désigner quelqu'un.**

DEMO.md a aussi été mis à jour : branche à extraire, nombre de tests, lecture des
runs `en_cours`.

---

## Vérification directe de la base `pmmp_veille`

Connexion réelle : `pmmp_app@localhost:5432/pmmp_veille`, le 25/09/2026 à
**16:00:35 (Africa/Casablanca, +00:00)**, PostgreSQL 18.6.

### État réel des données

| Table | Lignes |
|---|---|
| `consultations` | **0** |
| `historique_modifications` | **0** |
| `collecte_runs` | **0** |

- **Dernier run** : **aucun**. `collecte_runs` est vide, `v_dernier_run_reussi`
  renvoie `NULL`.
- **Le run de ce matin n'a rien inséré, parce qu'il n'y a pas eu de run ce
  matin.** La tâche `PMMP-Veille` démarre pour la première fois le **26/09/2026 à
  06:00** (`NextRunTime`). Son seul déclenchement, **manuel, le 25/09 à 11:46**, a
  été **refusé hors fenêtre** (`LastTaskResult = 2`), et un refus n'écrit rien en
  base. `storage/logs/` est vide (le log de ce test a été supprimé après
  l'audit). `storage/last_run.json` date du 24/09 à 20:52 (`echec`, `shutdown`,
  `run_id` null).
- **Run bloqué en `en_cours`** : **aucun**.
- **Lignes orphelines** : **0** (historique sans consultation : 0 ; historique
  avec un `run_id` inexistant : 0 ; doublons de clé naturelle : 0).
- Détail : la séquence `consultations_id_seq` est à 3 alors que la table est vide.
  Ce sont les `INSERT … RETURNING` des contrôles de droits (24/09 et 25/09), faits
  en transaction annulée : une séquence PostgreSQL ne recule pas. Sans
  conséquence ; `collecte_runs_id_seq` n'a jamais servi, donc le premier run
  portera le n°1.

### Schéma réel comparé à `db/schema.sql` — ✅ conforme

- 3 tables (propriétaire `pmmp`), 1 vue, 7 index. Colonnes, types, `NOT NULL` et
  valeurs par défaut sont identiques au fichier, colonne par colonne. Toutes les
  dates sont en `timestamp with time zone`.
- **Aucune colonne ni table ajoutée aujourd'hui** : la reprise s'appuie sur les
  colonnes existantes, le verrou anti-double-instance est un fichier et la
  détection des runs morts réutilise `statut` / `raison`.

### Contraintes, encodage, fuseau — ✅

- Clé naturelle `consultations_cle_naturelle UNIQUE (org_acronyme,
  ref_consultation)`.
- Clés étrangères `historique_modifications.consultation_id → consultations(id)
  ON DELETE CASCADE` et `historique_modifications.run_id → collecte_runs(id)`.
- `CHECK` sur `collecte_runs.statut`, `consultations.statut` et
  `historique_modifications.type_evenement`.
- Encodage : base, serveur et client en **UTF8**. Collation
  `English_United States.1252` (inchangée, point connu : ordre de tri seulement).
- Fuseau : `TimeZone=Africa/Casablanca` au niveau de la base et de la session.

### Droits de `pmmp_app` — ✅ 14/14 (refaits le 25/09)

Le schéma et `roles.sql` n'ont pas été modifiés. Les 14 contrôles du 24/09 ont
quand même été refaits :

| # | Contrôle | Résultat |
|---|---|---|
| 1–5 | `SELECT`, `INSERT … RETURNING`, `UPDATE`, `SELECT … FOR UPDATE`, lecture de `v_dernier_run_reussi` | autorisés ✅ |
| 6–10 | `DELETE`, `TRUNCATE`, `CREATE TABLE`, `DROP TABLE`, `ALTER TABLE` | refusés (`InsufficientPrivilege`) ✅ |
| 11–13 | connexion aux bases `postgres`, `pmmp_test`, `template1` | refusée (« User does not have CONNECT privilege ») ✅ |
| 14 | connexion avec l'ancien rôle `pmmp` | refusée ✅ (`pg_roles` : `rolcanlogin = false`) |

Attributs du rôle : non superutilisateur, sans `CREATEDB`, `CREATEROLE`,
réplication ni `BYPASSRLS`, `NOINHERIT`, 10 connexions au plus, membre d'aucun
rôle. Droits : `INSERT, SELECT, UPDATE` sur les 3 tables, `SELECT` sur la vue.

---

## Validation finale

- ✅ Fonctionnel : vérifié sur faux portail, pages réelles capturées et 109 tests. **Jamais exécuté sur le vrai portail au-delà de la page 1 de la capture du 23/09.**
- ✅ Cas d'erreur testés (manquent : gros volume, perte de la base en cours de run)
- ✅ Pas de mot de passe dans le code (ni dans l'historique Git)
- ✅ Configuration externalisée
- ✅ Logs disponibles (log par run, `collecte_runs`, `last_run.json`). Compteurs d'erreurs seulement dans le JSON `stats`.
- ✅ Pas de doublons si relancé, en base comme pour les DCE. **Le HTML brut des pages de liste est réécrit à chaque run.**
- ❌ Automatisation testée : chaque maillon a été testé (tâche déclenchée à la main, run dans la fenêtre sur faux portail, verrou, runs morts), **mais la tâche ne s'est jamais déclenchée à son heure réelle**. Première fois : 26/09 à 06:00.
- ❌ Résultat contrôlé manuellement : **aucun résultat réel à contrôler**, `pmmp_veille` est vide. Seuls des résultats sur faux portail et fixtures ont été vérifiés (par requêtes SQL).
- ✅ Documentation disponible
- ✅ Procédure de rollback disponible pour le code. **Pour les données, aucune sauvegarde n'existe.**

## Peut-on ajouter une API par-dessus tout de suite ?

**Oui, pour une API en lecture seule.** Elle doit tourner dans un processus
séparé, sans modifier `src/pmmp_collector/` ni le schéma, et se connecter avec un
compte PostgreSQL en lecture seule à créer. Ce compte ne doit **pas** être
`pmmp_app`, qui peut écrire. **Non, si l'API doit écrire en base ou modifier le
schéma** : sans sauvegarde de la base et sans alerte en cas d'échec, une erreur ne
serait ni rattrapable ni signalée.

À savoir avant de la montrer : la base est **vide** jusqu'au premier run réel du
26/09 à 06:00. D'ici là, l'API n'aurait rien à afficher, sauf à la brancher sur la
base de test.
