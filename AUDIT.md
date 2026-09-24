# Audit du collecteur PMMP — 24/09/2026

Branche `audit-2026-09-24`, partie de `main` @ `996121f`. Aucun push, aucun merge.
Périmètre : revue, correction et vérification de l'existant. **Aucune nouvelle
fonctionnalité** n'a été ajoutée.

**Conclusion : OUI, le projet est prêt à être testé sans erreur bloquante** (détail
et réserves à la fin du document).

## Résumé

| Point | Statut | En bref |
|---|---|---|
| A. Revue de code | **corrigé** | 2 bugs de parsing sur les vraies pages, fuseau en dur, fichier parasite |
| B. Règles de collecte | **OK** | Toutes appliquées dans le code ; vérifiées par un vrai crawl sur un faux portail local |
| C. Tests automatisés | **corrigé** | 5 échecs au départ → 86/86 verts ; 20 tests ajoutés |
| D. Base PostgreSQL | **OK** | Schéma et contraintes conformes ; cycle complet validé sur les pages réelles |
| E. README / reproductibilité | **corrigé** | Suivi depuis zéro ; étapes Windows et base de test ajoutées, section obsolète corrigée |
| F. Robustesse | **corrigé** | Les erreurs 404/500 faisaient perdre des consultations en silence ; blocage si la base ne répond pas |
| G. Secrets | **OK** | Aucun secret dans le code ni dans l'historique Git |
| H. Rotation des identifiants | **OK** | Compte `pmmp_app` à moindre privilège ; ancien mot de passe révoqué ; A à G revérifiés |

---

## A. Revue de code — corrigé

Relu : `__main__.py`, `config.py`, `settings.py`, `middlewares.py`, `extensions.py`,
`pipelines.py`, `db.py`, `history.py`, `models.py`, `parsers.py`, `storage.py`,
`spiders/pmmp.py`, `db/schema.sql`, `scripts/`, `tests/`. Aucune erreur de syntaxe,
aucun import cassé (`compileall` OK). Les API Scrapy utilisées
(`DOWNLOAD_DELAY_JITTER`, `close_spider_async`) existent bien dans la version 2.19 installée.

Valeurs lues depuis `.env` : URL de base, chemin de recherche, chaîne de connexion,
User-Agent, délai, fenêtre horaire, fuseau et seuils du circuit breaker. Les
valeurs par défaut de `config.py` sont les mêmes que dans `.env.example`.

| Commit | Fichier | Problème | Correction |
|---|---|---|---|
| `a185698` | `parsers.py` | Sur les **5 vraies fiches détail**, la date limite n'était jamais extraite : le libellé « Date et heure limite de remise des plis : » est seul dans son bloc, et la valeur est dans le bloc voisin. | `extract_labelled` lit aussi le bloc qui suit le parent quand le libellé est seul. |
| `a185698` | `parsers.py` | `pick(lab, "resultat")` compare par préfixe et attrapait le libellé de pagination « Résultats par page » : `resultat = 'Aller à la page'` sur **toutes** les fiches réelles, donc de faux événements `resultat` dans `historique_modifications`. | `resultat` : correspondance exacte ; `attributaire` et `titulaire` restent par préfixe. Test de non-régression ajouté. |
| `e5d3864` | `db.py` (+ appelants) | Le fuseau de la session PostgreSQL était codé en dur (`Africa/Casablanca`), sans lire `PMMP_TIMEZONE`. | `db.connect(url, timezone)` reçoit `cfg.tz.key`. |
| `f0376b9` | `src/main.py` | Script d'exemple PyCharm (« Hi, PyCharm »), sans rapport avec le projet. | Supprimé. |

Note : `models.TZ` reste `Africa/Casablanca` en dur. C'est volontaire : c'est le
fuseau dans lequel **le portail** affiche ses dates, pas un réglage du collecteur.

## B. Conformité aux règles de collecte — OK

Toutes les règles sont appliquées dans le code, pas seulement décrites en commentaire.
Le nouveau test `tests/test_crawl_integration.py` lance un **vrai**
`python -m pmmp_collector crawl` contre un faux portail sur `127.0.0.1`. Il vérifie
les requêtes réellement reçues par ce serveur. Aucune requête n'a été envoyée à
marchespublics.gov.ma pendant l'audit.

| Règle | Où | Vérifié par |
|---|---|---|
| `CONCURRENT_REQUESTS = 1` (+ par domaine) | `settings.py` | `test_rules` + **au plus 1 requête simultanée reçue** par le faux portail |
| `DOWNLOAD_DELAY` lu depuis l'env (plancher 1 s), sans jitter, AutoThrottle actif | `settings.py`, `config.py` | `test_rules`, `test_config` + **écart ≥ 1 s mesuré entre chaque requête reçue** |
| Refus hors fenêtre horaire sauf `--force` | `__main__.py` + `TimeWindowMiddleware` | `test_middlewares` + crawl réel : **code 2, zéro requête** ; `--force` : run plafonné |
| User-Agent TACHFIR sur les vraies requêtes | `DeclaredUserAgentMiddleware` (UA Scrapy désactivé) | **UA reçu identique sur 100 % des requêtes, y compris robots.txt** |
| Aucun contournement | pas de proxy (middleware désactivé), aucune rotation, captcha seulement **détecté** (arrêt ou suspension des DCE, jamais résolu) | `test_no_circumvention_code` + relecture (grep proxy/random/rotation/captcha) |
| Circuit breaker | `CircuitBreakerMiddleware` | **Crawl réel avec fiches en HTTP 503 : arrêt après 3 erreurs, les 3 fiches suivantes jamais demandées**, statut `echec`, raison `circuit_breaker`. En désactivant le middleware, le test échoue (6 requêtes au lieu de 3) : il détecte bien une régression. |

## C. Tests automatisés — corrigé

| | Au départ | À la fin |
|---|---|---|
| Tests collectés | 66 | 86 |
| Résultat sans base de test | 59 ✅ · **5 ❌** · 2 ignorés | **82 ✅ · 0 ❌** · 4 ignorés (tests PostgreSQL) |
| Résultat avec base de test | tests PostgreSQL jamais exécutés | **86 ✅ · 0 ❌ · 0 ignoré** |

Les 5 échecs de départ étaient `test_real_detail_page[*]` : date limite introuvable
sur les vraies fiches (voir A). Ils ont été corrigés dans le code, pas dans les tests.

Tests ajoutés (uniquement pour couvrir l'existant) :

- `tests/test_crawl_integration.py` (6) : règles de collecte sur un vrai crawl (B),
  échec rapide et lisible si la base est inutilisable (F), deux crawls complets avec
  base (upsert, `collecte_runs`, `run_id` dans l'historique).
- `tests/test_robustness.py` (13) : cas limites (F).
- `tests/test_db.py` (+1) : cycle complet sur les pages réelles (D).
- `tests/test_live_fixtures.py` : assertion de non-régression sur `resultat`.

Couverture des parties critiques : upsert (`test_db`, `test_crawl_integration`),
détection des changements (`test_history`, `test_db`), validation Pydantic
(`test_models`, `test_robustness`), téléchargement DCE (`test_spider_offline`,
`test_robustness`, `test_crawl_integration`), `PRADO_PAGESTATE` (`test_parsers`,
`test_spider_offline`, `test_live_fixtures`).

**Relancer les tests** (venv activé, racine du projet) :

```powershell
pytest                                   # 82 passed, 4 skipped  (~40 s)

# Avec les tests PostgreSQL, sur la base JETABLE pmmp_test (déjà créée sur ce PC) :
$env:PMMP_TEST_DATABASE_URL = "postgresql://postgres:<mot de passe postgres>@localhost:5432/pmmp_test"
pytest                                   # 86 passed  (~70 s)
$env:PMMP_TEST_DATABASE_URL = $null
```

## D. Base PostgreSQL — OK

- `db/schema.sql` appliqué **deux fois** sans erreur sur une base vierge
  (`CREATE DATABASE … ENCODING 'UTF8' TEMPLATE template0`) : il est idempotent.
  `init-db` a aussi été vérifié.
- Contraintes, vérifiées dans le catalogue `pg_constraint` :
  `consultations_cle_naturelle UNIQUE (org_acronyme, ref_consultation)`. Toutes les
  dates sont en `timestamp with time zone` (les 8 colonnes de date). Base en `UTF8`, fuseau de
  la base `Africa/Casablanca`. Des `CHECK` limitent `statut` et `type_evenement`, et
  des clés étrangères relient `historique_modifications` à `consultations`
  (`ON DELETE CASCADE`) et à `collecte_runs`. Tout est conforme à la description
  du schéma et du README.
- **Cycle complet sur les pages réelles** (`test_full_cycle_on_live_fixtures`) : les
  5 fiches de `fixtures/live/` passent dans les vraies pipelines (validation, puis
  upsert et historique).
  1. Insertion : 5 lignes, aucun historique, `12/11/2026 10:00` du portail restitué
     `12/11/2026 10:00` dans le fuseau `Africa/Casablanca`.
  2. Même rejeu : **aucun doublon**, aucun historique.
  3. Rejeu modifié : `historique_modifications` contient exactement
     `date_limite_depot` + `statut` (`report_date`), `objet` (`rectificatif`),
     `statut` → `annule` (`annulation`) et `resultat` (`resultat`), avec l'ancienne
     et la nouvelle valeur et le `run_id`.
- Refait avec le compte `pmmp_app` sur `pmmp_veille` (point H) : deux crawls réels
  contre le faux portail, 6 consultations sans doublon, 12 lignes d'historique
  rattachées au 2ᵉ run, aucune ligne orpheline. **La base a ensuite été vidée**
  (`TRUNCATE … RESTART IDENTITY`) : elle était vide avant l'audit et l'est de nouveau.
- Données existantes : `pmmp_veille` était vide (0 consultation, 0 run). Aucune
  donnée orpheline, aucune contrainte manquante.

À surveiller : voir « Points à surveiller » (collation Windows, runs interrompus).

## E. README et reproductibilité — corrigé

Suivi depuis zéro : clone neuf de la branche dans un dossier temporaire, venv neuf,
`pip install -r requirements.txt`, `pip install -e .`, `cp .env.example .env`,
`status`, `pytest`, `scrapy list`, puis `crawl`, qui refuse hors fenêtre.
**Toutes ces commandes fonctionnent telles qu'écrites.** Les étapes base de données
(§4) ont été rejouées en PowerShell sur la vraie base.

`.env.example` contient **toutes** les variables utilisées par le code (19/19,
vérifié par recherche automatique).

| Commit | Problème | Correction |
|---|---|---|
| `98871ca` | §7 : `PMMP_MODE=test python …` et `PMMP_TEST_DATABASE_URL=… pytest` sont en syntaxe bash, inutilisables tels quels sous PowerShell. | Équivalents PowerShell ajoutés. |
| `98871ca` | §7 : « base jetable » sans expliquer comment la créer (connaissance non écrite). | Commandes de création de `pmmp_test`. |
| `98871ca` | §10 disait que le code n'avait « pas encore été exécuté contre le vrai portail », alors que `fixtures/live/` contient une capture du 23/09. | Section mise à jour. |
| `98871ca` | §4.3 demandait de remplir `.env` avant de dire comment le créer. | Création de `.env` indiquée à cet endroit. |
| `1f475a1` | §4 : un seul compte `pmmp` propriétaire, utilisé par l'application. | Nouveau déroulé : propriétaire `pmmp` sans connexion, tables créées via `SET ROLE pmmp`, compte `pmmp_app` créé par `db/roles.sql`. |
| `98871ca`, `1f475a1` | Tableau des erreurs incomplet. | Nouveaux messages ajoutés. |

## F. Robustesse et gestion d'erreurs — corrigé

| Commit | Fichier | Problème | Correction |
|---|---|---|---|
| `a95e7db` | `spiders/pmmp.py` | Dans Scrapy, `HttpError` (réponse 404/500) **hérite de `IgnoreRequest`**. Les 3 errbacks faisaient `if failure.check(IgnoreRequest): return` pour ignorer les requêtes annulées par nos middlewares. Résultat : **fiche détail en 404/500** → consultation perdue sans log ; **lien DCE en 404/500** → consultation déjà analysée jamais enregistrée ; **page de liste en 500** → aucune trace. | `_cancelled_by_us()` exclut `HttpError`. Les erreurs HTTP sont loggées, comptées, et l'item est conservé. |
| `c64de33` | `db.py` | Pas de `connect_timeout` : une base qui ne répond pas **bloquait le collecteur plus de 2 minutes** (constaté pendant le test). | `connect_timeout=10`. |
| `f4898f0` | `__main__.py` | Base absente en prod, mot de passe refusé ou tables manquantes : l'erreur survenait dans `open_spider` et s'affichait en traces Twisted `CRITICAL: Unhandled error in Deferred`. C'est ce qui a produit le `storage/last_run.json` de 20:52 (`prod`, `shutdown`). | `crawl` vérifie la base **avant** Scrapy (et après la fenêtre horaire). Message clair, code 1, aucune requête au portail. |
| `5d89b90` | `scripts/run_nightly.ps1` | Sous PowerShell 5.1, `$ErrorActionPreference = "Stop"` combiné à la redirection de stderr d'un exécutable natif transforme **la première ligne de log Scrapy en erreur fatale**. Le script s'arrêtait avec le code 1 (au lieu du vrai code) et un log vide. `*>>` écrivait en outre en UTF-16. La tâche planifiée aurait échoué **chaque nuit**. | Redirection faite par `cmd.exe`. Vérifié : code 2 hors fenêtre, log lisible en UTF-8. |

Cas limites vérifiés par `tests/test_robustness.py`. Chacun est **loggé** et
**n'interrompt pas le run** :

| Cas | Comportement vérifié |
|---|---|
| Date limite manquante, vide, illisible (`bientôt`, `32/13/2026`), invraisemblable (`1900`) | Item écarté (`WARNING Consultation écartée org/ref … date_limite_depot`), compteur `pmmp/items_invalid`, l'item suivant passe |
| Lien DCE absent | `dce_statut = aucun_lien`, item enregistré |
| Fiche détail introuvable (404) ou timeout | `ERROR Échec de la fiche détail`, données de la liste conservées (`dce_statut = echec_fiche_detail`) |
| DCE en 404 ou timeout | `ERROR Échec du téléchargement DCE`, item enregistré avec `dce_statut = echec` |
| Page de liste en timeout | `ERROR`, les fiches déjà listées sont quand même visitées |
| HTML inattendu (page de maintenance) sur la liste ou la fiche | Loggé, aucune exception ; fiche : données de la liste conservées |
| Pannes répétées | Circuit breaker (voir B) |

## G. Sécurité et secrets — OK

- **Code actuel** : aucun identifiant réel. Seules des valeurs d'exemple apparaissent
  (`CHANGE_ME`, `mot_de_passe`, `<mot de passe généré>`). Le mot de passe de `.env`
  n'apparaît dans **aucun autre fichier** du dépôt (recherche exacte).
- **`.gitignore`** : `.env`, `.venv/`, `storage/*` (sauf les `.gitkeep`) et `.idea/`
  sont ignorés, confirmé par `git check-ignore -v`.
  `fixtures/live/` est versionné volontairement : c'est le jeu de test de passation
  (≈ 1,5 Mo).
- **Historique Git** (`git log --all -p` : les 2 commits d'origine et ceux de l'audit).
  gitleaks et trufflehog ne sont pas installés sur ce PC, j'ai donc fait une
  recherche équivalente par motifs : URL avec mot de passe, `password=`, `secret`,
  `api_key`, `token=`, clés privées, clés AWS, jetons GitHub. Résultat : **aucun
  secret trouvé**. Seules des valeurs d'exemple ressortent. Recherche exacte des mots
  de passe réels (ancien et nouveau `.env`, superutilisateur) : **0 occurrence**.
  Le dossier `.idea/` du premier commit (`7747c92`) ne contient ni source de données
  ni mot de passe. **Rien à signaler, aucune réécriture d'historique nécessaire.**

## H. Rotation des identifiants — OK

Fait en dernier, une fois A à G validés.

- **`pmmp_app`** (nouveau, `LOGIN`, non superutilisateur, sans `CREATEDB` ni
  `CREATEROLE`, 10 connexions au plus) : `CONNECT` sur `pmmp_veille`
  **uniquement** ; `SELECT, INSERT, UPDATE` sur les 3 tables ; `USAGE, SELECT` sur
  leurs séquences ; `SELECT` sur la vue de supervision. Des droits par défaut sont
  prévus pour les futures tables de `pmmp`.
- **`pmmp`** (ancien compte applicatif) : reste propriétaire de la base et des
  tables, mais passe en **`NOLOGIN`, mot de passe supprimé**. L'ancien mot de passe
  est donc révoqué.
- Le droit de connexion de `PUBLIC` a été retiré sur les autres bases de ce serveur
  (`postgres`, `template1`, `pmmp_test`), sinon `pmmp_app` aurait pu s'y connecter.
- Script versionné et rejouable : `db/roles.sql` (commit `8097f5a`). Le mot de passe
  est lu dans `PMMP_APP_PASSWORD` : il n'est ni dans le fichier ni sur la ligne de
  commande. `log_statement = none` sur ce serveur, donc il n'est pas non plus dans
  les logs PostgreSQL.
- Mot de passe : 32 caractères aléatoires (module `secrets` de Python), écrit
  **uniquement** dans `.env` (ignoré par Git), jamais dans `.env.example`.

Vérification des droits réels avec les identifiants du `.env` (14 contrôles, tous
conformes) : `SELECT`, `INSERT … RETURNING`, `UPDATE`, `SELECT … FOR UPDATE` et
lecture de la vue sont **autorisés** ; `DELETE`, `TRUNCATE`, `CREATE TABLE`,
`DROP`, `ALTER` et la connexion aux bases `postgres`, `pmmp_test` et `template1`
sont **refusés** ; la connexion avec l'ancien rôle `pmmp` est **refusée**.

**Checklist A à G relancée avec ces identifiants** : `compileall` OK ; 86/86 tests ;
deux crawls réels sur le faux portail écrivant dans `pmmp_veille` avec `pmmp_app`
(voir D) ; `status` OK ; `crawl` refusé hors fenêtre (code 2) ; `run_nightly.ps1`
(code 2) ; nouveau scan des secrets (0 occurrence). Les étapes §4.2 à §4.6 du README
ont été rejouées en PowerShell.

---

## 🔑 Nouveaux identifiants de connexion à la base

| | |
|---|---|
| Hôte / port | `localhost:5432` |
| Base | `pmmp_veille` |
| **Utilisateur** | **`pmmp_app`** |
| **Mot de passe** | **volontairement absent de ce fichier** : affiché dans le terminal à la fin de l'audit, et présent dans `.env` (ligne `PMMP_DATABASE_URL`, entre `pmmp_app:` et `@`) |

Pourquoi il n'est pas écrit ici : `AUDIT.md` est commité. Écrire le mot de passe
ici le mettrait dans l'historique Git, ce que les consignes G et H interdisent.
Enregistrez-le dans votre gestionnaire de mots de passe.

**Mots de passe encore actifs à changer vous-même :**

1. **Superutilisateur `postgres`** : son mot de passe actuel est faible et il a été
   communiqué en clair pendant la session d'audit. **À changer** :
   `psql -U postgres -h localhost -c "\password postgres"`. Il n'est utilisé nulle
   part dans le projet, sauf pour les tests sur `pmmp_test` et l'administration.
2. **DataGrip** : si une connexion y utilise l'utilisateur `pmmp`, elle ne
   fonctionne plus (`pmmp` ne peut plus se connecter). Utilisez `pmmp_app` pour
   consulter les données, ou `postgres` pour l'administration.
3. L'ancien mot de passe de `pmmp` est **révoqué** (`PASSWORD NULL` + `NOLOGIN`) :
   rien à faire.

---

## Points à surveiller (non bloquants)

1. **Aucun crawl complet n'a encore tourné sur le vrai portail** : il n'y a eu
   qu'une capture de 1 page et 5 fiches (23/09). Le premier run de nuit est le
   vrai test grandeur nature : regardez `storage/logs/`, `storage/last_run.json`
   et `SELECT * FROM collecte_runs`. La liste annonce 10 063 pages : au rythme
   imposé (≥ 3 s par requête, une à la fois), un crawl complet ne tiendra **pas**
   dans une seule nuit (runs `partiel`, code 3). C'est le comportement prévu,
   mais il faut en tenir compte, par exemple avec `PMMP_MAX_PAGES`.
2. **`acheteur` et `lieu_execution` diffèrent entre la liste et la fiche** (liste :
   « LE DIRECTEUR PROVINCIAL… », fiche : « M3 / DPESK - LE DIRECTEUR… »). Si une
   fiche échoue une nuit, ce sont les données de la liste qui sont enregistrées,
   ce qui crée un faux `rectificatif` dans l'historique (inversé à la nuit
   suivante).
3. Un run tué brutalement (arrêt du PC, kill) reste en `en_cours` dans
   `collecte_runs`. La supervision (`v_dernier_run_reussi`) ne regarde que les
   succès et n'est donc pas faussée.
4. Collation de la base locale : `English_United States.1252` (défaut Windows).
   Pas d'effet sur le stockage de l'arabe (UTF-8), seulement sur l'ordre de tri.
   Sur le serveur Linux, créez la base avec une locale UTF-8.
5. `tzdata` 2026.4 donne `Africa/Casablanca` = UTC+0 en ce moment (horodatages
   `+00:00`). C'est correct selon cette version ; gardez `tzdata` à jour
   (`pip install -U tzdata`), car le Maroc change parfois ses règles.
6. `scripts/run_nightly.sh` (Linux) : seule sa syntaxe a été vérifiée
   (`bash -n`), pas son exécution (PC Windows). Vérifiez que `flock` est présent
   sur le serveur.
7. `reservation_pme` n'apparaît sur aucune des pages réelles capturées (valeur
   `NULL`) et `date_publication` ne vient que de la liste.
8. `db/roles.sql` retire le droit de connexion de `PUBLIC` sur toutes les autres
   bases du serveur. Sur un serveur **partagé**, prévenez l'administrateur (voir
   README §4.4).
9. La base de test `pmmp_test` est conservée sur ce PC pour les tests PostgreSQL.

## Conclusion

**Oui, le projet est prêt à être testé par vous sans erreur bloquante.**

Les erreurs bloquantes trouvées sont toutes corrigées et couvertes par un test :
- la date limite n'était pas extraite des vraies fiches ;
- des consultations étaient perdues en silence sur les réponses 404/500 ;
- la tâche planifiée Windows plantait dès la première ligne de log ;
- le crawl se bloquait si la base ne répondait pas ;
- les erreurs de base s'affichaient en traces Twisted illisibles.

La suite est entièrement verte (86/86 avec la base, 82 + 4 ignorés sans), et le
README fonctionne tel qu'écrit depuis zéro.

Il ne reste rien à régler avant la suite (logs/cron, README final, passation). Deux
actions de votre côté :
1. enregistrer le nouveau mot de passe `pmmp_app` et changer celui de `postgres`
   (section 🔑) ;
2. lancer le premier run de nuit **après 23:00** avec
   `python -m pmmp_collector crawl --max-pages 2`, puis vérifier `last_run.json`.
