# Vérification de l'alignement avec la feuille de route — 27/09/2026

Vérification menée le 27/09/2026 entre 00:06 et 00:20 (heure du PC, Africa/Casablanca),
sur la branche `corrections-2026-09-26` @ `aef87a0` (arbre propre, poussée sur
`origin`). Référence : « Feuille de route — Moteur de veille des appels d'offres
(PMMP) », mise à jour du 22/09/2026 avec l'arbitrage du chef de projet.

**Périmètre respecté :** aucun fichier existant modifié, aucun commit, aucune requête vers
marchespublics.gov.ma, tâche planifiée seulement lue (`Get-ScheduledTask`,
`Get-ScheduledTaskInfo`). Requêtes SQL en `default_transaction_read_only=on` sur
`pmmp_veille`. Une API temporaire a tourné sur le port 8001 (arrêtée ensuite).
`ng build` a régénéré `frontend/dist/`, qui est ignoré par Git. Les scripts de
vérification (requêtes SQL, blocage réseau pour pytest) sont restés dans le dossier
temporaire de la session. Ce rapport est le seul fichier créé dans le dépôt.

`REVUE_2026-09-26.md` a été lue d'abord. Chaque point a été revérifié plutôt que recopié.

## Synthèse

| Verdict sur l'énoncé d'origine | Nombre | Points |
|---|---|---|
| Confirmé tel quel | 12 | 3, 4, 7, 8, 10, 11, 12, 13, 15, 16, 17, 19 |
| À nuancer / partiellement suivi | 4 | 2, 6, 14, 18 |
| Énoncé d'origine faux | 4 | 1, 5, 9, 20 |

---

## Phase 1 — Cadrage

### 1. Retrait de la « demande écrite à la TGR » et de la « validation juridique » mentionné comme contexte — **Pas suivi (énoncé d'origine faux)**

- **Preuve :** recherche `TGR|validation juridique|juridique|arbitrage` dans tout le dépôt
  (code, `*.md`, scripts, interface, hors `node_modules`/`.venv`/`storage`) :
  **aucune occurrence**. Les seules occurrences de « 22/09 » sont des dates de publication
  dans `fixtures/live/liste/page0001.html`.
- Les règles de collecte sont présentées comme « consignes du chef de projet »
  (`settings.py:3`, `config.py:21`, `README.md:25`), mais la décision du 22/09 n'est
  citée nulle part.
- **Ce que ça change :** rien dans le dépôt n'explique au lecteur pourquoi la
  collecte se fait sans accord écrit de la TGR ni validation juridique. Ce contexte
  n'existe que dans la feuille de route.

### 2. Règles de collecte dans `settings.py` — **Suivi pour les 5 règles demandées, à nuancer pour la fenêtre horaire**

- **Une requête à la fois :** `settings.py:22-23`, `CONCURRENT_REQUESTS = 1`,
  `CONCURRENT_REQUESTS_PER_DOMAIN = 1`.
- **Délai entre requêtes :** `settings.py:25-26`, `DOWNLOAD_DELAY = _cfg.download_delay`
  et `DOWNLOAD_DELAY_JITTER = 0`. Le `.env` réel contient `PMMP_DOWNLOAD_DELAY=3`. Un
  plancher est codé : `config.py:137`, `ConfigError` si le délai est sous
  `MIN_DOWNLOAD_DELAY`. AutoThrottle ne peut que ralentir (`settings.py:28-31`).
- **Pas de nouvelle tentative :** `RETRY_ENABLED = False` (`settings.py:33`).
- **robots.txt :** `ROBOTSTXT_OBEY = True` (`settings.py:18`).
- **User-Agent :** `.env` réel
  `PMMP_USER_AGENT=TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)`.
  `config.py:130` refuse un UA Scrapy ou un UA sans « TACHFIR ». L'UA est imposé sur
  chaque requête par `DeclaredUserAgentMiddleware` (`settings.py:47-48`).
- **Proxy et captcha :** `HttpProxyMiddleware: None` (`settings.py:45`). Aucune variable
  `*proxy*` dans l'environnement. Un captcha provoque un arrêt, sans contournement :
  `spiders/pmmp.py:162-163` (`CloseSpider("captcha_detecte")`) et `:414-420` (DCE
  suspendus).
- **Test garde-fou :** `tests/test_rules.py:44-56` échoue si
  `playwright|selenium|…|2captcha|…|curl_cffi|impersonate` apparaît dans `src/`. Le test
  passe.
- **Nuance importante, hors des 5 règles citées :** la **fenêtre horaire** imposée par
  le chef (nuit, 23:00–06:00, « non négociable ») **n'est pas suivie**. Elle est
  réglée à **06:00–10:00** (`.env` `PMMP_ALLOWED_WINDOW=06:00-10:00`, `config.py:152`).
  C'est une « décision du stagiaire, 25/09/2026 », documentée honnêtement
  (`README.md:13-20` et `:34`, `scripts/run_nightly.ps1:2-4`). Elle reste un écart par
  rapport à la consigne.

### 3. « Si le site bloque ou ralentit : arrêt immédiat » — **Suivi, et déclenché en conditions réelles**

- **Code :** `middlewares.py:26`, `STOP_NOW_STATUSES = {403, 429}` (arrêt immédiat).
  `:86-148` : arrêt après N problèmes consécutifs (5xx, timeouts, réponse lente). Le
  `.env` réel contient `PMMP_CB_MAX_CONSECUTIVE=3` et `PMMP_CB_SLOW_SECONDS=15`.
  Le middleware est placé à 990, au plus près du téléchargeur (`settings.py:51`).
- **Déclenchement réel** (`storage/logs/run_20260926_060002.log`) :
  - l. 116, 118 et 120 : `Problème 1/3`, `2/3`, `3/3` (ConnectionLost), à 06:42:29,
    06:42:32 et 06:42:35 ;
  - l. 121 : `CRITICAL: CIRCUIT BREAKER DÉCLENCHÉ — arrêt immédiat du run, aucune
    nouvelle tentative` ;
  - l. 122 : `Closing spider (circuit_breaker)`.
- **En base :** `collecte_runs` n°3 est en statut `echec`, terminé à 06:42:35.
- **Point de process, non vérifiable dans le dépôt :** la consigne demande aussi une
  « discussion avec le chef de projet » après un arrêt. Il faut le confirmer avec toi :
  le dépôt ne peut pas montrer si cette discussion a eu lieu après l'arrêt du 26/09.
  Fait lié : aucun mécanisme ne prévient qui que ce soit d'un arrêt (voir point 17).

## Phase 2 — Collecte fiable

### 4. Formulaires rejoués en HTTP direct (Scrapy), sans navigateur — **Suivi**

- `spiders/pmmp.py:15` : `from scrapy.http import FormRequest`.
- `:138-140` et `:233-238` : `FormRequest` avec `PRADO_POSTBACK_TARGET` et
  `PRADO_POSTBACK_PARAMETER`.
- `:313-319` : le postback PRADO renvoie le formulaire reçu avec son `PRADO_PAGESTATE`.
- Aucun navigateur, ni par défaut ni ailleurs (voir point 5).

### 5. Playwright seulement en secours — **Énoncé d'origine faux : Playwright est totalement absent, et interdit**

- Aucune occurrence dans `requirements.txt`, `pyproject.toml` ni
  `frontend/package.json`.
- `pip list` dans `.venv` : ni `playwright` ni `selenium`.
- `tests/test_rules.py:45` **interdit** explicitement `playwright|selenium|puppeteer` dans
  `src/`.
- **Ce que ça change :** il n'existe **aucun mécanisme de secours** par navigateur.
  Si le portail cesse d'accepter les postbacks rejoués, la collecte s'arrête. Aucun
  repli n'est prévu. (La revue du 26/09 a utilisé `playwright-core` hors du projet,
  uniquement pour tester l'interface.)

### 6. Historique des versions — **Partiellement suivi : schéma et code en place, table vide**

- **Schéma :** `db/schema.sql:66-76`. La table `historique_modifications` contient
  `champ`, `ancienne_valeur`, `nouvelle_valeur`,
  `type_evenement ∈ {rectificatif, report_date, annulation, resultat, autre}`,
  `detecte_le timestamptz` et `run_id`.
- **Code :** `pipelines.py:88-91` (`compute_changes` puis `insert_history` dans la même
  transaction que l'upsert). `db.py:125-139` écrit aussi la clôture automatique dans
  l'historique.
- **Données réelles :** `select count(*) from historique_modifications` → **0**.
- **Ce que ça change :** le mécanisme n'a encore jamais produit une ligne en conditions
  réelles, faute de deux collectes successives des mêmes fiches. Les 26 valeurs
  réparées le 26/09 par `scripts/reparer_doublons.py` n'y figurent pas non plus.

### 7. Déduplication par clé naturelle + upsert — **Suivi**

- `db/schema.sql:57` : `CONSTRAINT consultations_cle_naturelle UNIQUE (org_acronyme, ref_consultation)`.
- `db.py:40-42` : `INSERT … ON CONFLICT (org_acronyme, ref_consultation) DO UPDATE SET`.
- `pipelines.py:87-90` : `fetch_for_update` (verrou), puis upsert.
- **Requête sur les doublons**
  (`… group by org_acronyme, ref_consultation having count(*)>1`) → **0**.

### 8. Validation (Pydantic) avant insertion — **Suivi**

- `settings.py:54-57` : `ValidationPipeline` (100) passe avant `PostgresPipeline` (300).
- `pipelines.py:25-36` : `Consultation.model_validate`, puis `DropItem` et le compteur
  `pmmp/items_invalid` en cas d'échec.
- `collecte_runs.nb_ecartees` vaut 0 pour les 3 runs.

### 9. Stockage des fichiers bruts hors fixtures — **Énoncé d'origine faux pour le HTML (c'est fait), partiellement vrai pour les DCE**

- **Module dédié :** `src/pmmp_collector/storage.py:28-60`, `HtmlArchiver`. Il écrit les
  octets bruts dans `storage/raw_html/<horodatage du run>/<type>/…html`, plus un index
  `storage/raw_html/index.jsonl` (URL, méthode, statut, type, clé, date, **sha256**).
- **Copie en fixtures seulement en mode test** : `spiders/pmmp.py:96` passe
  `fixtures_dir=… if self.cfg.is_test else None`.
- **Pages archivées :** `spiders/pmmp.py:128`, `151`, `342` et `413` archivent
  `recherche`, `liste`, `detail` et `dce_intermediaire`.
- **Sur disque :** `find storage/raw_html -name '*.html' | wc -l` → **868** fichiers,
  `du -sh` → **133 Mo**, `index.jsonl` → 871 lignes. En base,
  `raw_html_detail_path` est renseigné pour 20 consultations sur 23.
- **Ces archives ont déjà servi à une ré-analyse :** `scripts/reparer_doublons.py`
  (commit `0cab4a9`).
- **DCE :** le mécanisme existe (`DceStore`, `storage/dce`), mais le dossier contient
  **0 fichier** aujourd'hui. En base, `dce_statut` vaut `page_intermediaire` pour 20
  consultations et `echec_fiche_detail` pour 3, et `dce_paths` est vide partout. Les DCE
  ne sont donc pas collectés (formulaire de conditions d'utilisation non soumis ; la
  décision revient au chef, cf. REVUE §3.9). La revue du 26/09 comptait 1 DCE sur
  disque, il y en a 0 aujourd'hui.

### 10. Dates en `timestamptz`, fuseau Africa/Casablanca — **Suivi**

- `information_schema.columns` : les **9** colonnes de date sont en
  `timestamp with time zone`, sur `collecte_runs`, `consultations`,
  `historique_modifications` et la vue `v_dernier_run_reussi`.
- `current_setting('TimeZone')` → `Africa/Casablanca`.
- `pg_db_role_setting` → `TimeZone=Africa/Casablanca`, défini au niveau de la base.
- `.env` : `PMMP_TIMEZONE=Africa/Casablanca`.
- `db/schema.sql:7` : `SET TIME ZONE 'Africa/Casablanca'`.

## Transverse — Application et interface

### 11. FastAPI plutôt que Spring Boot — **Suivi (confirmé)**

- `api/main.py` expose 5 routes GET : `/health`, `/consultations`, `/consultations/{org}/{ref}`,
  `…/historique` et `/collecte/dernier-run`, plus `/` redirigé vers `/docs`.
- **Lancée sur le port 8001 :**
  - `/health` → 200
    `{"api":"ok","base":"ok","base_de_donnees":"pmmp_veille","lecture_seule":true}` ;
  - `/consultations` → 200, `total: 23` ;
  - `/collecte/dernier-run` → 200 (run 3, `echec`) ;
  - `…/q9t/1014491/historique` → 200 `[]` ;
  - `openapi.json` → titre « API PMMP (lecture seule) ».
- **Précision :** aucune API ne tournait au moment de la vérification (rien en écoute
  sur 8000 ni 4200). L'API se lance à la main (README §12), ce n'est pas un service
  permanent.

### 12. Interface Angular — **Suivi (toujours vrai)**

- `npx ng build` : succès (`Application bundle generation complete`).
- `npx ng test --watch=false` : **44/44** tests, 9 fichiers.
- Routes (`frontend/src/app/app.routes.ts`) : tableau de bord, consultations, fiche,
  suivi de la collecte, feuille de route, 404.
- Je n'ai pas refait les contrôles dans un navigateur de la revue du 26/09 : build et
  tests seulement.

### 13. Pas de backend Java, donc pas de table de tâches partagée Python ↔ Java — **Suivi (absence confirmée)**

- `git ls-files | grep -iE "\.java$|pom.xml|gradle"` → rien.
- `find` sur le disque (hors `node_modules` et `.venv`) → aucun `.java` ni `pom.xml`.
- Tables de `pmmp_veille` : `collecte_runs`, `consultations`,
  `historique_modifications`, et la vue `v_dernier_run_reussi`. **Aucune table de
  tâches ni de file d'attente.**

### 14. Fonctionnalités prioritaires — **À nuancer : 1 sur 6 présente, 1 partiellement, 4 absentes**

| Fonctionnalité | État | Preuve |
|---|---|---|
| Recherches sauvegardées | **Absente** | Il existe seulement `services/derniere-recherche.service.ts`, un signal en mémoire pour le bouton « Retour à la liste ». Les critères sont aussi mis dans l'URL (`liste-consultations.ts:196-198`), donc partageables par lien, mais rien n'est enregistré. La page Feuille de route les affiche « 🔜 Prévu » (`feuille-de-route.ts:46-48`, dans « Alertes ») |
| Fiche d'AO avec historique | **Présente** (mais l'historique est vide, point 6) | Route `consultations/:org/:ref`, section « Historique des modifications » (`consultation-detail.html:130`), API `…/historique` |
| Suivi commercial | **Absent** | Menu « À venir » avec l'étiquette « Bientôt » (`app.ts:31`), « 🔜 Prévu » (`feuille-de-route.ts:51-53`). Aucune colonne ni table en base |
| Calendrier des dates limites | **Partiel** : pas de vue calendrier | Tableau de bord « Prochaines échéances » (5 plus proches, `tableau-de-bord.ts:53`), tri par date limite (`api/main.py:115`), filtres `date_limite_avant`/`apres` (`api/main.py:88-89`) |
| Coffre-fort des attestations | **Absent** | Aucune occurrence de « coffre » ni d'« attestation » dans le code ou l'interface. Aucun stockage de fichiers d'entreprise |
| Exports Excel/CSV | **Absents** | Aucune occurrence de `csv`, `xlsx`, `excel` ni `FEEDS` dans `src/`, `api/`, `scripts/` ou `frontend/src/`. **« Export CSV toujours disponible » est faux** : le seul export est un JSONL (`storage/test_items.jsonl`) écrit **uniquement en mode test sans base** (`pipelines.py:57-61`). `FEED_EXPORT_ENCODING` (`settings.py:68`) n'est qu'un réglage : aucun flux n'est configuré, et la CLI (`__main__.py`) n'a pas d'option `-o` |

## Transverse — Exploitation

### 15. Pas de Docker Compose — **Suivi (absence confirmée)**

- `git ls-files | grep -iE "docker|compose"` → rien.
- `find . -iname "*docker*" -o -iname "*compose*.y*ml"` (hors `node_modules` et
  `.venv`) → rien.

### 16. Planification par le Planificateur de tâches Windows — **Suivi**

| Tâche | Déclencheur | Réglages | Dernier lancement | Prochain |
|---|---|---|---|---|
| `PMMP-Veille` | quotidien 06:00 | `WakeToRun=True`, `StartWhenAvailable=True`, `IgnoreNew`, limite 5 h, `Interactive` | 26/09 06:00:00, **résultat 1** (échec, circuit breaker) | **27/09 06:00** |
| `PMMP-Sauvegarde` | quotidien 11:30 | `WakeToRun=False`, `StartWhenAvailable=True`, `IgnoreNew`, limite 1 h, `Interactive` | 26/09 12:55:50, résultat 0 | 27/09 11:30 |

- Les deux tâches sont en état `Ready`, avec 0 lancement manqué.
- L'action de `PMMP-Veille` est
  `powershell.exe … -File …\scripts\run_nightly.ps1`.
- En `Interactive`, il n'y a pas de run si la session Windows est fermée.
- Le 27/09 à 00:07, il n'y a pas encore de journal `run_20260927_*`.

### 17. Aucune sonde de surveillance — **Suivi (absence confirmée)**

- Recherche `healthchecks|hc-ping|uptime|kuma|webhook|smtp|sendmail|notif` dans `src/`,
  `api/` et `scripts/` → **rien**.
- `scripts/run_nightly.ps1` se contente d'écrire un journal et de renvoyer un code de
  sortie.
- Seule existe la vue `v_dernier_run_reussi` (`db/schema.sql:80-85`, « à surveiller
  depuis un outil externe »), et rien ne la surveille.
- Le `/health` de l'API ne répond que si quelqu'un l'interroge.

### 18. Aucun contrôle qualité automatique + taux réel de dates limites manquantes — **Absence confirmée ; le chiffre demandé est à nuancer**

- **Absence :** recherche `qualit|nouvel avis|5 %|0.05|zero_new` dans `src/` → rien.
  Aucune alerte sur « zéro nouvel avis un jour ouvré » ni sur un « seuil de date
  limite manquante ».
- **Taux réel, requête exécutée :**
  `select count(*) filter (where date_limite_depot is null), count(*) from consultations`
  → **0 / 23 = 0,00 %**.
- **Nuance importante :** ce 0 % est **garanti par construction** et ne mesure pas la
  qualité de la collecte.
  - `date_limite_depot` est `NOT NULL` en base (`db/schema.sql:43`, et
    `information_schema.is_nullable = 'NO'`).
  - Une fiche sans date limite est rejetée par `ValidationPipeline` avant d'arriver en
    base.
  - Le bon indicateur est donc le taux de fiches **écartées**, soit
    `collecte_runs.nb_ecartees` ou le compteur `pmmp/items_invalid` : il vaut **0** sur
    les 3 runs.
  - L'échantillon reste très petit : 23 consultations, dont 20 issues de tests
    manuels.

### 19. Tests sur pages enregistrées, sans réseau — **Suivi**

- `tests/test_live_fixtures.py:14` et `tests/test_db.py:80` lisent `fixtures/live/`
  (liste, 5 fiches détail, 5 pages DCE intermédiaires, formulaire).
- `tests/test_spider_offline.py:148` utilise `fixtures/live/liste/page0001.html`.
- `tests/test_crawl_integration.py:127` et `:151` montent un faux portail
  (`ThreadingHTTPServer` sur `127.0.0.1:0`, avec `PMMP_BASE_URL` pointé dessus).
- **Exécution :** `pytest -q -rs`, avec un module qui bloque et journalise toute
  résolution DNS ou connexion hors machine :
  - résultat : **107 passés, 17 ignorés** (111 s) ;
  - `NETBLOCK: 0 tentative(s) hors machine`.
- **Recoupement avec la revue du 26/09 :** les 17 tests ignorés ont la même cause,
  `PMMP_TEST_DATABASE_URL non défini` (10 dans `test_api.py`, 3 dans
  `test_crawl_integration.py`, 4 dans `test_db.py`).
  - Il y a 105 tests passés dans la revue et 107 ici, parce que 2 tests sans base ont
    été ajoutés depuis.
  - Je ne les ai pas relancés avec une base jetable ; la revue §5 annonçait 124/124.

### 20. Aucune sauvegarde automatisée — **Énoncé d'origine faux pour la base, vrai pour le stockage**

- **La base est sauvegardée :** `scripts/backup_db.ps1` (commit `3d1e708`) lance
  `pg_dump -Fc` sur `pmmp_veille` et conserve les 14 plus récentes. Il est lancé par la
  tâche `PMMP-Sauvegarde`, chaque jour à 11:30 (point 16).
- **Sauvegardes présentes :** `storage/backups/pmmp_veille_20260926_{125459,125551,130017}.dump`
  (17 Ko chacune). Les journaux `storage/logs/backup_*.log` indiquent
  « Sauvegarde faite ».
- **Limites constatées :**
  - Le déclenchement automatique de 11:30 **n'a encore jamais eu lieu**. La tâche a été
    créée le 26/09 vers 12:55, et le premier passage est prévu le 27/09 à 11:30.
  - Les sauvegardes sont écrites **sur le même disque**, dans `storage/backups/`.
  - **Rien ne sauvegarde `storage/raw_html/` (133 Mo) ni `storage/dce/`** : le stockage
    brut n'a aucune sauvegarde.

---

## Constat hors des 20 points : risque pour le run de ce matin (27/09 06:00)

En interrogeant la base, `import psycopg` a échoué dans le `.venv` du projet :
`DLL load failed while importing pq: An Application Control policy has blocked this file`.

- Le blocage se reproduit depuis PowerShell, hors de la session de vérification.
- Le journal `Microsoft-Windows-CodeIntegrity/Operational` contient **18 événements
  3033/3077** sur la DLL `…\.venv\Lib\site-packages\psycopg_binary.libs\libpq-….dll`.
  Ils datent du 23/09 23 h, du 24/09 00 h et 20 h, et du 27/09 00 h.
- `VerifiedAndReputablePolicyState = 1` : **Smart App Control est actif**.
- Les runs du 25/09 16 h et du 26/09 06 h ont pourtant écrit en base, et aucun
  événement n'est enregistré à ces heures-là. Le blocage paraît donc **intermittent**
  (réputation évaluée à distance).
- Je ne peux pas prédire le run de 06:00 sans le lancer. S'il se reproduit à ce
  moment-là, le run s'arrêtera avant tout contact avec le portail (connexion base
  impossible, code 1).
- `README.md:80-85` documente ce cas et les solutions : `psycopg[c]` ou `psycopg` avec
  la `libpq` de PostgreSQL.
- Pour mes requêtes, je l'ai contourné sans rien modifier (`PSYCOPG_IMPL=python`, avec
  `C:\Program Files\PostgreSQL\18\bin` dans le `PATH` du seul processus).
