# pmmp_collector — moteur de veille PMMP (TACHFIR)

Collecteur des appels d'offres publiés sur le **Portail Marocain des Marchés
Publics** (https://www.marchespublics.gov.ma/pmmp/). Il fonctionne en **Scrapy,
HTTP pur** : pas de navigateur piloté. Les postbacks PRADO (champ caché
`PRADO_PAGESTATE`) sont rejoués directement. Les données sont stockées dans
**PostgreSQL** avec l'historique des versions.

Chaîne de traitement : `liste paginée → fiche détail → DCE → validation Pydantic → upsert PostgreSQL + historique`

---

> ⚠️ **Horaire de collecte modifié le 25/09/2026 : le matin (06:00–10:00),
> et non plus la nuit.** C'est une **décision du stagiaire**, qui **diffère de la
> consigne d'origine du chef de projet** (« nuit ou heures creuses uniquement »,
> 23:00–06:00, présentée comme non négociable). Ce n'est pas une correction
> technique. Toutes les autres règles ci-dessous sont inchangées. **Revenir à la
> nuit** ne demande de changer qu'une variable d'environnement,
> `PMMP_ALLOWED_WINDOW=23:00-06:00`, puis l'heure de la tâche planifiée
> (voir §8).

## 1. Pourquoi ces règles de collecte existent (à lire avant de toucher au code)

Le PMMP est un service public dont dépendent toutes les entreprises
soumissionnaires. Le chef de projet a imposé les règles suivantes. **Elles ne
sont pas négociables et priment sur la vitesse.** Chacune est codée en dur et
protégée par un test (`tests/test_rules.py`, `tests/test_config.py`,
`tests/test_middlewares.py`) : si quelqu'un l'assouplit, les tests échouent.

| Règle | Où elle est appliquée | Pourquoi |
|---|---|---|
| Une seule requête à la fois | `settings.py` : `CONCURRENT_REQUESTS = 1` | Ne jamais charger le serveur de plusieurs requêtes parallèles. |
| Pause entre requêtes (≥ 1 s, 3 s par défaut) + AutoThrottle | `settings.py`, plancher dans `config.py` | AutoThrottle ralentit automatiquement si le site ralentit. Il ne descend jamais sous le délai. |
| Fenêtre horaire (`PMMP_ALLOWED_WINDOW`). **Actuellement 06:00–10:00 Casablanca** (choix du stagiaire). Consigne d'origine : 23:00–06:00 | `__main__.py` (refus au démarrage) + `TimeWindowMiddleware` (refus à chaque requête, arrêt si la fenêtre se ferme) | Consigne d'origine : la collecte ne doit pas concurrencer les utilisateurs humains en journée. La fenêtre du matin s'en écarte en partie (voir l'encadré ci-dessus). |
| `--force` = test manuel **plafonné** | `spiders/pmmp.py` : 1 page / 10 consultations par défaut hors fenêtre | `--force` ne sert pas à lancer un crawl complet en journée. |
| User-Agent identifiable TACHFIR + contact | `config.py` (refuse un UA Scrapy/navigateur) + `DeclaredUserAgentMiddleware` | L'administrateur du portail doit savoir qui nous sommes et comment nous joindre. |
| Aucun contournement | Pas de proxy (middleware proxy désactivé), pas de captcha résolu, aucun en-tête usurpé. Test `test_no_circumvention_code` | Si le site nous limite, on s'arrête et on en parle avec lui. On ne force jamais le passage. |
| Circuit breaker | `CircuitBreakerMiddleware` : arrêt après N (défaut 3) erreurs 5xx, timeouts ou réponses lentes **consécutifs**. Arrêt **immédiat** sur HTTP 403/429 | Un site en difficulté ne doit jamais recevoir des tentatives en rafale. `RETRY_ENABLED = False`. |
| `robots.txt` respecté | `ROBOTSTXT_OBEY = True` | Politesse de base. |

Captcha : s'il apparaît sur une page de liste, le run s'arrête (`captcha_detecte`).
S'il apparaît sur une page DCE, les téléchargements de DCE sont suspendus pour le
reste du run. Aucun code de résolution de captcha ne doit être ajouté.

---

## 2. Prérequis

- **Python 3.11 ou plus** (testé avec 3.14 et Scrapy 2.19)
- **PostgreSQL 13 ou plus**, en local ou à distance
- Linux (cron) ou Windows (Planificateur de tâches)

## 3. Installation

Linux / macOS :

```bash
cd pmmp_collector
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                   # rend le paquet pmmp_collector importable
```

Windows (PowerShell) :

```powershell
cd pmmp_collector
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

> Si PowerShell refuse d'exécuter `Activate.ps1` (« l'exécution de scripts est
> désactivée sur ce système »), lancez une fois
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, puis réessayez.
> Sous `cmd.exe`, utilisez `.venv\Scripts\activate.bat`.

> Windows : si `import psycopg` échoue avec « An Application Control policy has
> blocked this file », la politique de sécurité du poste bloque la DLL de
> `psycopg[binary]`. Il faut soit installer PostgreSQL (qui fournit `libpq`) et
> utiliser `pip install "psycopg[c]"` ou `psycopg` seul, soit exécuter le
> collecteur sur le serveur Linux. Le mode test sans base fonctionne quand même
> (voir §6).

## 4. Créer la base

Cette étape se fait **une seule fois**, sur la machine où tourne PostgreSQL
(votre PC en local, ou le serveur Linux). Elle crée :

1. une **base** `pmmp_veille`, en UTF-8 (indispensable pour l'arabe) ;
2. un rôle **`pmmp`**, propriétaire de la base et des tables, **sans connexion
   possible** : il ne sert qu'à faire évoluer le schéma ;
3. les **tables**, à partir de `db/schema.sql` ;
4. un compte **`pmmp_app`**, le seul utilisé par le collecteur : il lit, insère
   et met à jour les données du projet, **rien d'autre** (ni suppression, ni
   modification du schéma, ni accès aux autres bases). Droits détaillés dans
   `db/roles.sql`.

Vous aurez besoin du **mot de passe du superutilisateur `postgres`**, choisi
lors de l'installation de PostgreSQL. Chaque commande `psql -U postgres` le
demande.

### 4.1 Vérifier que PostgreSQL tourne

**Windows (PowerShell)** : PostgreSQL s'installe dans
`C:\Program Files\PostgreSQL\<version>\` (ex. `18`), mais `psql` n'est
**pas** ajouté au `PATH`. Ajoutez-le pour la session en cours :

```powershell
$env:Path += ";C:\Program Files\PostgreSQL\18\bin"   # adapter 18 à votre version
Get-Service postgresql*          # Status doit être "Running"
pg_isready -h localhost -p 5432  # doit répondre "accepting connections"
```

Si le service est arrêté : `Start-Service postgresql-x64-18` (PowerShell en
administrateur). Pour ajouter `psql` au `PATH` de façon permanente : Paramètres
Windows → « Modifier les variables d'environnement système » → `Path` →
Nouveau → `C:\Program Files\PostgreSQL\18\bin`, puis rouvrir le terminal.

**Linux** :

```bash
sudo apt install postgresql          # Debian/Ubuntu, si ce n'est pas déjà fait
sudo systemctl status postgresql     # doit être "active (running)"
```

### 4.2 Créer le propriétaire et la base

**Windows (PowerShell)**, depuis n'importe quel dossier :

```powershell
psql -U postgres -h localhost -c "CREATE ROLE pmmp NOLOGIN;"
psql -U postgres -h localhost -c "CREATE DATABASE pmmp_veille OWNER pmmp ENCODING 'UTF8' TEMPLATE template0;"
psql -U postgres -h localhost -c "ALTER DATABASE pmmp_veille SET timezone TO 'Africa/Casablanca';"
```

**Linux** (on passe par le compte système `postgres`, sans mot de passe) :

```bash
sudo -u postgres psql -c "CREATE ROLE pmmp NOLOGIN;"
sudo -u postgres psql -c "CREATE DATABASE pmmp_veille OWNER pmmp ENCODING 'UTF8' TEMPLATE template0;"
sudo -u postgres psql -c "ALTER DATABASE pmmp_veille SET timezone TO 'Africa/Casablanca';"
```

Réponses attendues : `CREATE ROLE`, `CREATE DATABASE`, `ALTER DATABASE`.
Si une commande répond « existe déjà » (*already exists*), l'étape a déjà été
faite : passez à la suivante.

### 4.3 Créer les tables

Depuis la **racine du projet**. Les tables sont créées au nom de `pmmp`
(`SET ROLE pmmp`) pour qu'il en soit le propriétaire :

```powershell
psql -U postgres -h localhost -d pmmp_veille -c "SET ROLE pmmp" -f db/schema.sql
```

(Linux : `sudo -u postgres psql -d pmmp_veille -c "SET ROLE pmmp" -f db/schema.sql`.)

Le script est **idempotent** : on peut le rejouer sans perdre de données
(c'est aussi la commande à relancer après une mise à jour de `db/schema.sql`).

### 4.4 Créer le compte de l'application

Générez un mot de passe fort (32 caractères, sans caractère spécial d'URL) :

```bash
python -c "import secrets, string; a = string.ascii_letters + string.digits + '-_'; print(''.join(secrets.choice(a) for _ in range(32)))"
```

Puis, depuis la racine du projet (le mot de passe passe par une variable
d'environnement : il n'apparaît ni dans le script ni dans l'historique de `psql`) :

```powershell
$env:PMMP_APP_PASSWORD = "<mot de passe généré>"
psql -U postgres -h localhost -d pmmp_veille -f db/roles.sql
Remove-Item Env:PMMP_APP_PASSWORD
```

```bash
# Linux
PMMP_APP_PASSWORD='<mot de passe généré>' sudo --preserve-env=PMMP_APP_PASSWORD -u postgres psql -d pmmp_veille -f db/roles.sql
```

Réponse attendue : `Rôles appliqués : pmmp (propriétaire, NOLOGIN), pmmp_app (application).`
Pour **changer le mot de passe** plus tard, relancez simplement cette étape avec
un nouveau mot de passe, puis mettez `.env` à jour (4.5).

> Le script retire à `PUBLIC` le droit de connexion aux **autres** bases du
> serveur (sinon `pmmp_app` pourrait s'y connecter). Sur un serveur partagé avec
> d'autres applications, leurs rôles doivent avoir un `GRANT CONNECT` explicite.

### 4.5 Renseigner la connexion dans `.env`

Créez d'abord le fichier `.env` à la racine du projet s'il n'existe pas
(`cp .env.example .env`, ou `Copy-Item .env.example .env` sous PowerShell ; détail
des variables au §5), puis remplissez :

```ini
PMMP_DATABASE_URL=postgresql://pmmp_app:<mot de passe généré>@localhost:5432/pmmp_veille
```

Format : `postgresql://<utilisateur>:<mot de passe>@<hôte>:<port>/<base>`.
Remplacez `localhost` par l'adresse du serveur si la base est distante. Si un
mot de passe choisi à la main contient un caractère spécial, encodez-le
(`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `#` → `%23`, `%` → `%25`).
`.env` n'est jamais commité (il est dans `.gitignore`).

### 4.6 Vérifier

```bash
psql "postgresql://pmmp_app:<mot de passe généré>@localhost:5432/pmmp_veille" -c "\dt"
```

Vous devez voir `collecte_runs`, `consultations` et `historique_modifications`
(propriétaire `pmmp`).

> `python -m pmmp_collector init-db` applique aussi `db/schema.sql`, mais avec le
> compte de `PMMP_DATABASE_URL` : il fonctionne sur une base de test dont vous
> êtes propriétaire (§7), pas avec `pmmp_app` qui n'a pas le droit de modifier
> le schéma (message « Droits insuffisants »).

**Erreurs fréquentes**

| Message | Cause / solution |
|---|---|
| `psql : terme non reconnu` / `command not found` | `psql` n'est pas dans le `PATH` (voir 4.1). |
| `password authentication failed for user "postgres"` | Mauvais mot de passe `postgres` (celui de l'installation). |
| `password authentication failed for user "pmmp_app"` | Le mot de passe de `.env` ne correspond pas à celui de l'étape 4.4 : refaire 4.4 puis 4.5. |
| `password authentication failed for user "pmmp"` | Normal : `pmmp` n'a plus de connexion. Utiliser `pmmp_app` (application) ou `postgres` (administration, DataGrip…). |
| `permission denied for database …` | `pmmp_app` n'a accès qu'à `pmmp_veille` : vérifier le nom de base dans `.env`. |
| `connection refused` | Service PostgreSQL arrêté, ou mauvais port (voir 4.1). |
| `database "pmmp_veille" does not exist` | L'étape 4.2 n'a pas été faite, ou faute de frappe dans `.env`. |
| `PMMP_DATABASE_URL n'est pas renseignée.` | Ligne vide dans `.env`, ou commande lancée hors de la racine du projet. |
| `ÉCHEC avant démarrage … connexion PostgreSQL impossible` (au lancement de `crawl`) | Mot de passe, hôte ou base de `PMMP_DATABASE_URL` incorrects, ou service arrêté. Aucune requête n'a été envoyée au portail. |
| `ÉCHEC avant démarrage … les tables n'existent pas` | Faire d'abord l'étape 4.3. |
| `permission denied for table …` | Droits de `pmmp_app` absents : relancer l'étape 4.4. |
| `connection timeout expired` | Serveur PostgreSQL injoignable (hôte/port faux, pare-feu) : abandon après 10 s. |

Tables créées (détail commenté dans `db/schema.sql`) :

- `consultations` : état courant de chaque avis. Clé naturelle
  `UNIQUE (org_acronyme, ref_consultation)`, qui correspond aux paramètres
  `orgAcronyme` / `refConsultation` des URL du portail. La référence affichée
  (ex. `12/2026/AOO`) est stockée dans `reference`.
- `historique_modifications` : une ligne par champ modifié (`rectificatif`,
  `report_date`, `annulation`, `resultat`, `autre`).
- `collecte_runs` : journal des exécutions (statut, raison, statistiques).
- Vue `v_dernier_run_reussi` : pour la supervision.

## 5. Configuration (`.env`)

```bash
cp .env.example .env    # puis éditer .env
```

| Variable | Rôle | Défaut |
|---|---|---|
| `PMMP_BASE_URL` | URL de base de l'application (racine du domaine, **pas** `/pmmp/` qui n'est que la page d'accueil) | `https://www.marchespublics.gov.ma/` |
| `PMMP_SEARCH_PATH` | page listant les consultations en cours | `index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons` (si le portail affiche le formulaire de recherche, il est soumis avec ses valeurs par défaut) |
| `PMMP_DATABASE_URL` | connexion PostgreSQL (obligatoire en prod) | — |
| `PMMP_USER_AGENT` | UA déclaré (doit contenir TACHFIR) | `TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)` |
| `PMMP_DOWNLOAD_DELAY` | pause entre requêtes (s), minimum 1 | `3` |
| `PMMP_ALLOWED_WINDOW` / `PMMP_TIMEZONE` | fenêtre autorisée (voir l'encadré en tête et §8) | `06:00-10:00` / `Africa/Casablanca` |
| `PMMP_CB_MAX_CONSECUTIVE` / `PMMP_CB_SLOW_SECONDS` | circuit breaker (N entre 1 et 10) / seuil de lenteur | `3` / `15` |
| `PMMP_DOWNLOAD_TIMEOUT` | timeout par requête (s) | `30` |
| `PMMP_STALE_RUN_HOURS` | au-delà (h), un run resté `en_cours` est considéré comme mort (PC éteint, kill) et passé en `echec` au démarrage du run suivant | `6` |
| `PMMP_MODE` | `prod` ou `test` | `prod` |
| `PMMP_MAX_ITEMS` | taille du **lot** : fiches détail visitées au plus par run (0 = aucune limite) | `1200` |
| `PMMP_INCREMENTAL` | ne visiter que les consultations nouvelles, modifiées ou en échec (voir §6) | `true` |
| `PMMP_PAGE_SIZE` | résultats par page de liste : 10, 20, 50, 100 ou 500 | `100` |
| `PMMP_MAX_PAGES` | limite optionnelle de pages de liste (0 = aucune) | `0` |
| `PMMP_FORCE_MAX_PAGES` / `PMMP_FORCE_MAX_ITEMS` | plafonds d'un run `--force` hors fenêtre | `1` / `10` |
| `PMMP_DOWNLOAD_DCE` | télécharger les DCE | `true` |
| `PMMP_STORAGE_DIR` / `PMMP_FIXTURES_DIR` | dossiers de stockage | `storage` / `fixtures` |

Une valeur contraire aux règles (délai < 1 s, UA non identifiable, etc.) fait
**refuser le démarrage** avec un message explicite.

## 6. Lancer une collecte

Toujours depuis la racine du projet (c'est là que sont lus `.env` et `storage/`) :

```bash
python -m pmmp_collector status          # heure locale, fenêtre ouverte/fermée, dernier run
python -m pmmp_collector crawl           # crawl complet (refusé hors fenêtre)
python -m pmmp_collector crawl --force   # test manuel en journée : 1 page, 10 consultations max
python -m pmmp_collector crawl --force --max-items 3
```

`scrapy crawl pmmp` fonctionne aussi. La fenêtre horaire est alors appliquée par
le middleware.

Codes de sortie : `0` succès · `1` échec (erreur, circuit breaker, aucune
consultation extraite) · `2` refusé (hors fenêtre) · `3` partiel (la fenêtre
s'est fermée pendant le run) · `4` refusé (un autre run est déjà en cours).

**Un seul run à la fois** : `crawl` prend un verrou du système sur
`storage/.crawl.lock`. Un second lancement (à la main pendant la tâche planifiée,
par exemple) est refusé avec le code `4`, sans aucune requête. Le verrou est
libéré automatiquement à la fin du processus, même tué ou si le PC redémarre :
il n'y a jamais de fichier à supprimer à la main.

### Collecte par lots

Le portail liste environ **100 000 consultations**. Avec les règles de collecte
(une requête à la fois, ≥ 3 s d'écart), la fenêtre du matin (4 h) permet au plus
≈ 4 800 requêtes : tout visiter en un run est impossible. La collecte est donc
**incrémentale et découpée en lots** :

1. La liste est affichée à `PMMP_PAGE_SIZE` résultats par page (100 par défaut,
   soit ≈ 1 000 pages au lieu de 10 000). Le collecteur fait ce choix dans la
   liste déroulante du portail, comme un utilisateur.
2. Pour chaque ligne, la base indique si la consultation est **nouvelle**,
   **modifiée** d'après la liste (date limite, annulation ou report) ou **en
   échec** au run précédent. Seules celles-là sont visitées (fiche + DCE). Les
   autres ne coûtent aucune requête : seule `derniere_vue_le` est mise à jour.
3. Au plus `PMMP_MAX_ITEMS` fiches sont visitées par run (le **lot**). Le run
   s'arrête alors proprement.
4. **Reprise** : le run suivant repart de la page 1. Tout ce qui est déjà en
   base est sauté, donc le lot suivant continue là où le précédent s'est arrêté.
   Aucun fichier d'état : c'est la base qui sert de point de reprise. C'est plus
   sûr qu'un numéro de page mémorisé, car les nouvelles publications décalent
   les pages d'un jour à l'autre.

Ordre de grandeur, avec 1 200 fiches par run : la **première** collecte
complète prend ≈ 80 jours (≈ 100 000 consultations). Ensuite, chaque run ne
visite que les nouveautés et les modifications. Pour accélérer la première
collecte, désactivez temporairement les DCE (`PMMP_DOWNLOAD_DCE=false` : deux
fois moins de requêtes par consultation) ou augmentez le lot, à condition que le
run tienne dans la fenêtre : compter ≈ 3 s par page de liste, par fiche et par DCE.

Les compteurs `pmmp/fiches_a_visiter/<raison>` et `pmmp/fiches_a_jour` des
statistiques du run (`collecte_runs.stats`) indiquent ce qui a été visité et pourquoi.

Ordre de parcours : **toutes les pages de liste d'abord**. Chaque postback PRADO
renvoie le formulaire reçu avec le `PRADO_PAGESTATE` de la réponse précédente,
sans aucune requête intercalée. Viennent ensuite les fiches détail, puis les
DCE. Un avis vu sur deux pages n'est visité qu'une fois (filtre de doublons
Scrapy), et l'upsert garantit l'absence de doublon en base.

Ce qui est produit :

- `storage/raw_html/<AAAAMMJJ_HHMMSS>/{liste,detail,dce_intermediaire}/*.html` :
  pages **brutes**, octet pour octet, pour une ré-analyse sans re-solliciter le
  site. `storage/raw_html/index.jsonl` indique l'URL, la date et le sha256 de
  chaque page.
- `storage/dce/<org>__<ref>/` : fichiers DCE. Un DCE déjà présent n'est **pas**
  retéléchargé.
- `storage/last_run.json` / `storage/last_success.json` + table `collecte_runs`.
- Mode test sans base : les items sont écrits dans `storage/test_items.jsonl`.

## 7. Tests et fixtures

```bash
pytest                       # tous les tests, sans base (≈ 1 min)
```

Aucun test n'envoie de requête au vrai portail. `tests/test_crawl_integration.py`
lance de vrais crawls contre un **faux portail local** (`127.0.0.1`) : c'est lui
qui vérifie les règles de collecte sur les requêtes réellement envoyées
(circuit breaker, User-Agent, une requête à la fois, pause entre requêtes).

- `fixtures/synthetic/` : pages **synthétiques** qui reproduisent la structure
  supposée du portail. Elles servent aux tests unitaires.
- `fixtures/live/` : pages **réelles**. En `PMMP_MODE=test`, chaque page
  récupérée y est copiée automatiquement. `tests/test_live_fixtures.py` les
  rejoue alors pour vérifier que les sélecteurs extraient bien les champs
  obligatoires.
- Tests PostgreSQL (upsert, historique, clôture, cycle complet sur les pages
  réelles) : ils sont **ignorés** tant que `PMMP_TEST_DATABASE_URL` n'est pas
  défini. Ils **vident les tables** : utilisez une base jetable `pmmp_test`,
  jamais `pmmp_veille`. Création (une fois) avec le superutilisateur :

  ```powershell
  psql -U postgres -h localhost -c "CREATE DATABASE pmmp_test ENCODING 'UTF8' TEMPLATE template0;"
  psql -U postgres -h localhost -c "ALTER DATABASE pmmp_test SET timezone TO 'Africa/Casablanca';"
  ```

  Lancement :

  ```powershell
  # Windows (PowerShell)
  $env:PMMP_TEST_DATABASE_URL = "postgresql://postgres:MOT_DE_PASSE_POSTGRES@localhost:5432/pmmp_test"
  pytest
  Remove-Item Env:PMMP_TEST_DATABASE_URL
  ```

  ```bash
  # Linux
  PMMP_TEST_DATABASE_URL=postgresql://postgres:...@localhost:5432/pmmp_test pytest
  ```

**Capturer les fixtures réelles** (à faire une fois, dans la fenêtre horaire) :

```bash
# Linux
PMMP_MODE=test python -m pmmp_collector crawl --max-pages 1 --max-items 5
```

```powershell
# Windows (PowerShell)
$env:PMMP_MODE = "test"
python -m pmmp_collector crawl --max-pages 1 --max-items 5
Remove-Item Env:PMMP_MODE
```

Puis :

```bash
pytest tests/test_live_fixtures.py -v
git add fixtures/live   # ces pages servent à la passation
```

Hors fenêtre horaire, la commande est refusée : ajoutez `--force` (run plafonné).

## 8. Planifier l'exécution quotidienne

Horaire actuel : **tous les jours à 06:00**, début de la fenêtre
`PMMP_ALLOWED_WINDOW=06:00-10:00` (décision du stagiaire, différente de la
consigne d'origine : voir l'encadré en tête). Les scripts s'appellent toujours
`run_nightly.*` (nom historique, conservé pour ne rien casser).

**Windows (installé sur le PC de développement)** : tâche `PMMP-Veille` du
Planificateur de tâches. Elle lance `scripts/run_nightly.ps1`, qui écrit un log
dans `storage/logs/run_<date>.log` (redirection faite par `cmd.exe`, voir le
commentaire du script) et purge les logs de plus de 60 jours.

```powershell
schtasks /query /tn "PMMP-Veille" /v /fo LIST   # vérifier : Next Run Time, Last Result
Start-ScheduledTask -TaskName "PMMP-Veille"      # lancer à la main (hors fenêtre : refus, code 2)
Get-ScheduledTaskInfo -TaskName "PMMP-Veille"    # LastTaskResult = code de sortie (0/1/2/3/4)
```

Réglages : une seule instance à la fois ; lancée dès que possible si le PC
était éteint à 06:00 (hors fenêtre, le collecteur refuse seul) ; autorisée sur
batterie ; arrêtée après 5 h ; exécutée sous le compte Windows de l'utilisateur,
**session ouverte** (« Interactive only » : aucun mot de passe stocké). PC éteint,
en veille ou session fermée à 06:00 : pas de collecte ce jour-là. La commande
complète de création est en tête de `scripts/run_nightly.ps1`.

> La tâche exécute le code **de la branche Git actuellement extraite** dans le
> dossier du projet. Gardez extraite une branche qui contient l'audit et ce
> changement (ou mergez-les dans `main`) : l'ancien `run_nightly.ps1` de `main`
> plante dès la première ligne de log.

**Changer l'horaire** (par exemple revenir à la nuit) :

1. Dans `.env` : `PMMP_ALLOWED_WINDOW=23:00-06:00`.
2. Heure de la tâche au début de la nouvelle fenêtre :

   ```powershell
   Set-ScheduledTask -TaskName "PMMP-Veille" -Trigger (New-ScheduledTaskTrigger -Daily -At 23:00)
   ```

Si seule la variable change, la tâche de 06:00 sera refusée tous les jours
(code 2) : c'est sans danger, mais il n'y aura plus de collecte.

**Linux (cron)** : `scripts/run_nightly.sh` active le venv, empêche deux runs
simultanés (`flock`), écrit un log dans `storage/logs/` et purge les logs de
plus de 60 jours.

```cron
0 6 * * *  /opt/pmmp_collector/scripts/run_nightly.sh
```

**Supervision** (détecter une panne silencieuse) : alerter si le dernier succès a
plus de 26 h.

```sql
SELECT * FROM v_dernier_run_reussi;                       -- anciennete > 26h => alerte
SELECT * FROM collecte_runs ORDER BY id DESC LIMIT 10;
```

Un run « terminé » qui n'a extrait **aucune** consultation est enregistré en
`echec` (raison `aucune_consultation_extraite`). C'est le symptôme typique d'un
changement du HTML du portail.

Un run **tué** (PC éteint ou redémarré, processus arrêté) ne peut pas écrire sa
fin : sa ligne reste `en_cours`. Au démarrage suivant, `crawl` passe en `echec`
tout run `en_cours` depuis plus de `PMMP_STALE_RUN_HOURS` (6 h par défaut), avec
la raison `interrompu : …`, et l'écrit dans le log (`ATTENTION : le run n°…`).
`termine_le` reste vide : l'heure réelle de l'arrêt n'est pas connue.

## 9. Règles métier

- **Statut** : `annule` (avis d'annulation détecté) > `cloture` (date limite
  passée) > `reporte` (date limite repoussée par rapport à la base, ou avis de
  report) > `en_cours`. À la fin de chaque run réussi, les consultations dont la
  date limite est passée passent en `cloture`, sans aucune requête au site.
- **Historique** : il est calculé avant l'upsert en comparant la base et la
  nouvelle collecte, sur `statut`, `date_limite_depot`, `objet`, `resultat` et
  les autres champs descriptifs. Une valeur absente de la page n'efface jamais
  une valeur connue (`COALESCE`) et n'est pas comptée comme une modification.
- **Validation** (`models.py`) : champs obligatoires (`org_acronyme`,
  `ref_consultation`, `objet`, `acheteur`, `date_limite_depot`, `url_detail`),
  dates `jj/mm/aaaa [hh:mm]` (chiffres arabes-indiens acceptés) converties en
  `timestamptz` Africa/Casablanca, texte normalisé en Unicode NFC (arabe et
  français). Un item invalide est journalisé puis écarté, sans arrêter le run.
- `reponse_electronique = true` signifie que la réponse électronique est
  **exigée** (obligatoire). Si elle est seulement autorisée ou refusée, la valeur
  est `false`. `reservation_pme = NULL` signifie que l'information n'apparaît pas
  sur la page.

## 10. Points à valider sur le site réel (reprise du projet)

Une capture réelle limitée a été faite le 23/09/2026 (formulaire de recherche,
1 page de liste, 5 fiches détail, 5 pages DCE intermédiaires) : ces pages sont
dans `fixtures/live/` et rejouées par `tests/test_live_fixtures.py` et
`tests/test_db.py`. Le crawl complet (toutes les pages) n'a pas encore été fait. Points à surveiller :

1. **URL** : corrigée après la première capture. `/pmmp/` renvoie la page
   d'accueil ; la liste est à la racine du domaine (lien « Consultations en cours »).
2. **Sélecteurs** (`src/pmmp_collector/parsers.py`, seul fichier à ajuster) :
   l'extraction repose surtout sur les libellés visibles (« Objet : »,
   « Acheteur public : »…), avec en secours les ids Atexo connus. Les noms des
   contrôles de pagination (`…numPageTop`, `…DefaultButtonTop`) sont détectés
   dans la page. Validés sur les pages capturées ; `reservation_pme` et
   `date_publication` n'apparaissent pas sur les fiches détail réelles
   (`date_publication` vient de la liste).
3. **Téléchargement du DCE** : si le lien mène à une page intermédiaire
   (formulaire, identification, acceptation de conditions), le collecteur
   l'archive, met `dce_statut = 'page_intermediaire'` et **ne la soumet pas**.
   Accepter des conditions d'utilisation au nom de TACHFIR est une décision du
   chef de projet. Si elle est prise, l'étape de soumission s'ajoute dans
   `save_dce` du spider.
4. **Annulation / report** : les formulations exactes du portail sont à
   confirmer dans `interpret_statut`.

## 11. Structure

```
pmmp_collector/
├── README.md, requirements.txt, pyproject.toml, scrapy.cfg, .env.example
├── db/schema.sql                 tables commentées + vue de supervision
├── db/roles.sql                  rôles pmmp (propriétaire) / pmmp_app (application)
├── src/pmmp_collector/
│   ├── __main__.py               CLI : crawl [--force], init-db, status
│   ├── config.py                 lecture/validation du .env, fenêtre horaire
│   ├── settings.py               réglages Scrapy (règles de collecte)
│   ├── middlewares.py            UA déclaré, fenêtre horaire, circuit breaker
│   ├── spiders/pmmp.py           parcours liste → détail → DCE
│   ├── parsers.py                extraction HTML (fonctions pures)
│   ├── models.py                 validation Pydantic
│   ├── history.py                statut + détection des modifications
│   ├── pipelines.py              validation, upsert PostgreSQL + historique
│   ├── db.py                     requêtes SQL
│   ├── extensions.py             suivi des runs, last_success.json
│   └── storage.py                archivage HTML brut, fichiers DCE
├── api/                          API de consultation en lecture seule (§12)
│   ├── main.py                   routes GET
│   ├── schemas.py                formats des réponses
│   └── db.py                     connexion lecture seule, 3 connexions au plus
├── storage/{dce,raw_html,logs}/
├── fixtures/{synthetic,live}/
├── tests/
└── scripts/run_nightly.sh, run_nightly.ps1
```

## 12. API de consultation (lecture seule)

> ⚠️ **Pas d'authentification : choix TEMPORAIRE.** N'importe qui pouvant joindre
> le port lit toutes les données. L'API doit donc rester sur `127.0.0.1` (poste
> local). **Avant tout accès depuis l'extérieur du poste** (autre machine, réseau,
> Internet, interface Angular hébergée ailleurs), il faut ajouter une
> authentification et HTTPS. Ne jamais la lancer avec `--host 0.0.0.0`.

Le dossier `api/` est un composant **séparé** du collecteur : il n'importe rien
de `src/pmmp_collector/` et ne fait que **lire** la base. Le collecteur reste seul
à écrire. Toutes les routes sont en `GET`. Un `POST`, `PUT` ou `DELETE` reçoit
`405`.

### Comment ça marche

```
Navigateur (ou Angular)  ──HTTP GET──▶  uvicorn (serveur web, port 8000)
                                              │
                                              ▼
                                        FastAPI : api/main.py (routes)
                                              │  api/db.py : session en lecture seule
                                              ▼
                                        PostgreSQL : base pmmp_veille
                                              ▲
Collecteur Scrapy (tâche planifiée) ──écrit──┘
```

- **uvicorn** est le serveur web. Il écoute sur `127.0.0.1:8000` et transmet
  chaque requête à FastAPI.
- **FastAPI** (`api/main.py`) choisit la route, vérifie les paramètres (un
  `statut` inconnu reçoit `422`) et renvoie du JSON. Il génère aussi tout seul la
  page `/docs`.
- À chaque requête, `api/db.py` ouvre une connexion **en lecture seule** avec
  `PMMP_DATABASE_URL` du `.env`, exécute la requête SQL, puis ferme la connexion.
- Le **collecteur** est le seul à écrire dans la base. L'API affiche ce qu'il a
  collecté, sans rien modifier. Les deux tournent indépendamment : l'API peut
  rester ouverte pendant un run.

### Avant la première utilisation (une seule fois)

1. Le projet est installé (§3) et la base existe (§4). Le `.env` contient
   `PMMP_DATABASE_URL`, le même que pour le collecteur.
2. Installer les dépendances de l'API (FastAPI, uvicorn), qui sont dans
   `requirements.txt` :

   ```powershell
   cd pmmp_collector              # dossier du projet
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

### Ouvrir l'API, étape par étape (Windows, PowerShell)

1. **Vérifier que PostgreSQL tourne** (voir aussi §4.1). Le résultat doit être
   `Running` :

   ```powershell
   Get-Service postgresql*
   ```

   S'il est arrêté : `Start-Service postgresql-x64-18`, dans un PowerShell
   ouvert en administrateur.

2. **Aller dans le dossier du projet** et activer l'environnement Python :

   ```powershell
   cd pmmp_collector              # dossier du projet
   .venv\Scripts\Activate.ps1
   ```

3. **Lancer l'API** :

   ```powershell
   python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
   ```

   Sans activer l'environnement, cette commande seule fait la même chose :

   ```powershell
   .venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
   ```

   L'API est prête quand le terminal affiche :

   ```
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
   ```

   **Laisser ce terminal ouvert** : fermer la fenêtre arrête l'API.

4. **Ouvrir dans le navigateur** : **<http://127.0.0.1:8000/docs>**.
   L'adresse <http://127.0.0.1:8000> affichée par uvicorn y redirige aussi.

5. **Arrêter l'API** : dans le terminal, `Ctrl+C`.

Après une modification du code, il faut arrêter (`Ctrl+C`) puis relancer l'API
pour qu'elle soit prise en compte.

### Utiliser la page /docs (Swagger)

Chaque route y est testable dans le navigateur. Cette page sert aussi de
démonstration si l'interface Angular n'est pas prête.

1. Cliquer sur une route, par exemple `GET /consultations`.
2. Cliquer sur **Try it out**.
3. Remplir les paramètres voulus, par exemple `statut` = `en_cours` et `limit` =
   `5`, ou les laisser vides.
4. Cliquer sur **Execute**. La réponse JSON s'affiche sous **Response body**,
   avec son code (`200`, `404`…). L'adresse exacte appelée s'affiche sous
   **Request URL** ; elle peut être copiée dans le navigateur.

Parcours conseillé pour une démonstration :

| Étape | Route | Ce qu'elle montre |
|---|---|---|
| 1 | `GET /health` | L'API tourne, connectée à `pmmp_veille` en lecture seule. |
| 2 | `GET /collecte/dernier-run` | La collecte a tourné : heure, statut, nombre de consultations. |
| 3 | `GET /consultations` avec `statut` = `en_cours` | Les appels d'offres en cours, échéance la plus proche d'abord. |
| 4 | `GET /consultations/{org_acronyme}/{ref_consultation}` | Le détail d'une consultation. Copier `org_acronyme` et `ref_consultation` depuis l'étape 3. |
| 5 | La même route avec une référence inventée | Réponse `404` propre. |

Chaque route s'ouvre aussi directement dans la barre d'adresse du navigateur,
par exemple :

- <http://127.0.0.1:8000/health>
- <http://127.0.0.1:8000/consultations?statut=en_cours&limit=5>
- <http://127.0.0.1:8000/consultations?categorie=travaux>
- <http://127.0.0.1:8000/collecte/dernier-run>

### En cas de problème

| Symptôme | Cause | Solution |
|---|---|---|
| `{"detail":"Not Found"}` (404) sur <http://127.0.0.1:8000> | Version de l'API antérieure à la redirection, ou API lancée avant la mise à jour du code | Ouvrir <http://127.0.0.1:8000/docs>, ou arrêter puis relancer l'API. |
| `ModuleNotFoundError: No module named 'api'` | Commande lancée hors du dossier du projet | Aller dans le dossier du projet (`cd pmmp_collector`), puis relancer. |
| `No module named uvicorn` ou `No module named fastapi` | Dépendances non installées, ou `.venv` non activé | `pip install -r requirements.txt` avec le `.venv` activé, ou utiliser `.venv\Scripts\python -m uvicorn …`. |
| `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)` | Une API tourne déjà sur le port 8000 (souvent dans un autre terminal) | Utiliser celle qui tourne, ou l'arrêter (`Ctrl+C` dans son terminal). Sinon, lancer sur un autre port avec `--port 8001` puis ouvrir <http://127.0.0.1:8001/docs>. |
| `/health` répond `{"api":"ok","base":"indisponible"}` (503) | PostgreSQL arrêté, `.env` introuvable (commande lancée hors du projet) ou mot de passe incorrect | Vérifier `Get-Service postgresql*` (démarrage : §4.1) et `PMMP_DATABASE_URL` dans `.env`. La cause exacte s'affiche dans le terminal de l'API. |
| La page ne s'ouvre pas du tout (« connexion refusée ») | L'API n'est pas lancée, ou son terminal a été fermé | Refaire l'étape 3. |
| `/consultations` renvoie `"total": 0` | La base est vide : aucun run n'a encore collecté de données | Normal avant le premier run ; voir `/collecte/dernier-run`. |

### Routes

| Route | Rôle |
|---|---|
| `GET /health` | L'API répond et la base est joignable. Indique la base utilisée et la lecture seule. `503` si la base est injoignable. |
| `GET /consultations` | Liste triée par date limite de dépôt, la plus proche d'abord. Filtres : `categorie`, `acheteur` (texte contenu, casse ignorée), `statut` (`en_cours`, `cloture`, `annule`, `reporte`), `date_limite_avant` (exclue), `date_limite_apres` (incluse). Pagination : `limit` (1 à 200, 50 par défaut), `offset`. `total` = nombre de résultats pour ces filtres. |
| `GET /consultations/{org_acronyme}/{ref_consultation}` | Détail d'une consultation. `404` si elle n'existe pas. |
| `GET /consultations/{org_acronyme}/{ref_consultation}/historique` | Modifications détectées, de la plus ancienne à la plus récente. `[]` si aucune. `404` si la consultation n'existe pas. |
| `GET /collecte/dernier-run` | Dernier run du collecteur (statut, heures, durée, raison, compteurs et erreurs) et date du dernier run réussi. `dernier_run` vaut `null` si aucun run n'a encore eu lieu. |

Exemples : `/consultations?statut=en_cours&categorie=travaux`,
`/consultations?date_limite_apres=2026-10-01&date_limite_avant=2026-11-01&limit=20`.

Les dates sont en ISO 8601 avec le décalage de l'heure du Maroc
(`Africa/Casablanca`). Ce décalage change selon la date : `+01:00` ou `Z`
(UTC+0). Une date donnée sans heure ni fuseau dans un filtre (`2026-10-01`)
signifie minuit, heure du Maroc.

### Risque accepté : compte `pmmp_app`

`CHECKLIST.md` recommandait un compte PostgreSQL **en lecture seule** dédié à
l'API. Le 25/09, le choix a été d'utiliser `pmmp_app`, qui a aussi les droits
`INSERT` et `UPDATE`, sans créer de nouveau rôle. Garde-fous en place
(`api/db.py`) :

- chaque session est ouverte en lecture seule (`default_transaction_read_only=on`).
  Toute écriture échoue (`ReadOnlySqlTransaction`), ce qui est vérifié par un
  test. **Ce n'est pas une barrière de droits** : une requête
  `SET default_transaction_read_only = off` la lèverait. Aucune requête de l'API
  ne le fait et aucune ne construit de SQL à partir des valeurs reçues (tout
  passe en paramètres) ;
- une requête est coupée après 5 s et la connexion abandonnée après 5 s ;
- **3 connexions au plus** en même temps. `pmmp_app` est limité à 10 connexions
  et le collecteur a besoin des siennes. Au-delà, l'API répond `503` ;
- sessions repérables dans `pg_stat_activity` (`application_name = 'pmmp_api'`).

Pour supprimer ce risque : créer un rôle avec `SELECT` seulement sur les 3 tables
et la vue, `CONNECT` sur `pmmp_veille` seulement, puis mettre ses identifiants
dans une variable propre à l'API.

### Tests

`tests/test_api.py`, lancé avec les autres par `pytest`. Deux tests tournent
sans base : aucune route d'écriture, et `503` propre si la base est injoignable.
Les autres ont besoin de la base jetable `pmmp_test` (`PMMP_TEST_DATABASE_URL`,
voir §7). Ils la **vident**, y insèrent un petit jeu de données connu, puis
vérifient chaque route, les filtres, la pagination, les `404` et le refus des
écritures.
