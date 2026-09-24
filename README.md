# pmmp_collector — moteur de veille PMMP (TACHFIR)

Collecteur des appels d'offres publiés sur le **Portail Marocain des Marchés
Publics** (https://www.marchespublics.gov.ma/pmmp/). Il fonctionne en **Scrapy,
HTTP pur** : pas de navigateur piloté. Les postbacks PRADO (champ caché
`PRADO_PAGESTATE`) sont rejoués directement. Les données sont stockées dans
**PostgreSQL** avec l'historique des versions.

Chaîne de traitement : `liste paginée → fiche détail → DCE → validation Pydantic → upsert PostgreSQL + historique`

---

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
| Heures creuses uniquement (23:00–06:00 Casablanca par défaut) | `__main__.py` (refus au démarrage) + `TimeWindowMiddleware` (refus à chaque requête, arrêt si la fenêtre se ferme) | La collecte ne doit pas concurrencer les utilisateurs humains en journée. |
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
| `PMMP_ALLOWED_WINDOW` / `PMMP_TIMEZONE` | fenêtre autorisée | `23:00-06:00` / `Africa/Casablanca` |
| `PMMP_CB_MAX_CONSECUTIVE` / `PMMP_CB_SLOW_SECONDS` | circuit breaker (N entre 1 et 10) / seuil de lenteur | `3` / `15` |
| `PMMP_DOWNLOAD_TIMEOUT` | timeout par requête (s) | `30` |
| `PMMP_MODE` | `prod` ou `test` | `prod` |
| `PMMP_MAX_PAGES` / `PMMP_MAX_ITEMS` | limites optionnelles (0 = aucune) | `0` |
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
s'est fermée pendant le run).

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

**Capturer les fixtures réelles** (à faire une fois, de préférence dans la
fenêtre de nuit) :

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

## 8. Planifier l'exécution nocturne

**Linux (cron)** : `scripts/run_nightly.sh` active le venv, empêche deux runs
simultanés (`flock`), écrit un log dans `storage/logs/` et purge les logs de
plus de 60 jours.

```cron
30 23 * * *  /opt/pmmp_collector/scripts/run_nightly.sh
```

**Windows** : `scripts/run_nightly.ps1`. La commande d'enregistrement de la
tâche est en tête du fichier (tâche quotidienne à 23:30, `MultipleInstances IgnoreNew`).

**Supervision** (détecter une panne silencieuse) : alerter si le dernier succès a
plus de 26 h.

```sql
SELECT * FROM v_dernier_run_reussi;                       -- anciennete > 26h => alerte
SELECT * FROM collecte_runs ORDER BY id DESC LIMIT 10;
```

Un run « terminé » qui n'a extrait **aucune** consultation est enregistré en
`echec` (raison `aucune_consultation_extraite`). C'est le symptôme typique d'un
changement du HTML du portail.

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
`tests/test_db.py`. Le crawl complet (toutes les pages, en fenêtre de nuit)
n'a pas encore été fait. Points à surveiller :

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
├── storage/{dce,raw_html,logs}/
├── fixtures/{synthetic,live}/
├── tests/
└── scripts/run_nightly.sh, run_nightly.ps1
```
