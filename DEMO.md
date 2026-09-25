# Démo de passation — 25/09/2026 après-midi (1 h)

Toutes les commandes sont en **PowerShell**, à taper **depuis la racine du
projet** (`C:\Users\abder_r9rl0a3\pmmp_collector`).

**À dire dès le début de la démo :**

- **Aucune collecte automatique n'a encore tourné.** La tâche planifiée
  démarre pour la première fois **demain 26/09 à 06:00**.
- **La base de production `pmmp_veille` est vide.** Elle a été vidée après
  l'audit du 24/09.
- Les données montrées viennent des **5 vraies consultations capturées sur le
  portail le 23/09** (`fixtures/live/`), rejouées dans la base de test
  `pmmp_test`.

L'après-midi, la fenêtre de collecte (06:00–10:00) est **fermée** : un crawl
complet est refusé, et c'est voulu. La démo s'appuie sur ce refus.

---

## 0. Préparation — 20 min avant, sans public

```powershell
cd C:\Users\abder_r9rl0a3\pmmp_collector
chcp 65001                                  # accents lisibles dans la console
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\Activate.ps1
git branch --show-current                   # checklist-2026-09-25 (contient les correctifs du 25/09 après-midi)
```

**Remplir la base de test avec les 5 vraies consultations** (demande le mot de
passe `postgres`) :

```powershell
$pw = Read-Host "Mot de passe postgres"
$env:PMMP_TEST_DATABASE_URL = "postgresql://postgres:$([uri]::EscapeDataString($pw))@localhost:5432/pmmp_test"
pytest tests/test_db.py -k full_cycle -v    # attendu : 1 passed
$env:PMMP_TEST_DATABASE_URL = $null
```

Ce test vide `pmmp_test`, insère les 5 consultations réelles, puis rejoue des
modifications : un report, un rectificatif, une annulation, un résultat. Il ne
vide pas la base à la fin, donc les données restent disponibles pour l'étape 4.

- **Plan B** si le mot de passe `postgres` est refusé ou si PostgreSQL ne répond
  pas : sauter cette préparation. L'étape 4 passe alors à son plan B, sans base.
- **À vérifier aussi** : ouvrir DataGrip avec une connexion
  `postgres@localhost:5432/pmmp_test`, prête pour l'étape 4.

---

## 1. Ce qui est prévu, et ce qui a vraiment tourné (5 min)

```powershell
schtasks /query /tn "PMMP-Veille" /v /fo LIST | Select-String "Next Run|Last Run|Last Result|Task To Run|Start Time|Comment"
```

À montrer :
- `Next Run Time : 9/26/2026 6:00:00 AM` : le premier vrai lancement est demain.
- `Last Result : 2` : il vient d'un lancement manuel le 25/09 à 11:46, **hors
  fenêtre**. Le collecteur a refusé de démarrer, sans aucune requête au portail.
- Le commentaire de la tâche signale l'écart à la consigne : matin au lieu de
  nuit.

```powershell
Get-ChildItem storage\logs                  # vide : aucun run planifié encore
python -m pmmp_collector status             # heure, fenêtre fermée, derniers runs
```

`status` affiche deux runs :

| Run | Ce que c'était |
|---|---|
| 23/09 | Capture de test, en mode `test` |
| 24/09 | Échec pendant l'audit : base injoignable. Le bug a été corrigé depuis (AUDIT.md, section A). |

Pas de plan B nécessaire : tout est local.

---

## 2. Les règles de collecte et le garde-fou horaire (10 min)

Ouvrir `README.md` : l'encadré en tête (horaire du matin), puis le tableau du §1
(pourquoi chaque règle existe).

```powershell
python -m pmmp_collector crawl
$LASTEXITCODE                               # 2 = refusé
```

Attendu : `REFUS : il est 15:xx (Africa/Casablanca), hors de la fenêtre
autorisée 06:00-10:00…`, code **2**. **Aucune requête n'est partie vers le
portail.** C'est la preuve que la règle horaire est appliquée par le code, pas
par la discipline de l'opérateur.

```powershell
Get-Content .env | Select-String "WINDOW|TIMEZONE|DELAY|MAX_ITEMS|USER_AGENT"
```

À montrer : pour revenir à la nuit, il suffit de changer une ligne
(`PMMP_ALLOWED_WINDOW=23:00-06:00`).

Pas de plan B nécessaire : aucun réseau.

---

## 3. Une collecte complète en direct, sur le faux portail local (10 min)

Les tests démarrent un **faux portail** sur le PC (127.0.0.1) et lancent le vrai
collecteur contre lui. Le vrai site n'est **jamais** contacté. Durée ≈ 45 s.

```powershell
pytest tests/test_crawl_integration.py -k "refuses or accepted or nominal or circuit" -v
```

Attendu : `4 passed`. Ce que prouve chaque test :

| Test | Ce qu'il prouve |
|---|---|
| `refuses_outside_window` | Hors fenêtre : refus, zéro requête. |
| `accepted_inside_window` | Dans la fenêtre : le crawl démarre sans `--force`. |
| `nominal_crawl_respects_collection_rules` | Une seule requête à la fois, ≥ 3 s d'écart, User-Agent TACHFIR, 100 résultats par page, DCE téléchargés. |
| `circuit_breaker_stops_real_crawl` | Le site répond mal : le collecteur s'arrête seul au lieu d'insister. |

**Plan B** si ça dure trop ou échoue : lancer seulement le refus horaire
(≈ 5 s) :

```powershell
pytest tests/test_crawl_integration.py -k refuses -v
```

Puis montrer le code des tests dans `tests/test_crawl_integration.py`, lignes
204-230 : les assertions sur les règles.

### Option : 10 consultations sur le VRAI portail — à décider avant la démo

```powershell
python -m pmmp_collector crawl --force      # plafonné : 1 page, 10 consultations
```

> ⚠️ Cette commande contacte le **vrai site en pleine journée** (≈ 20 requêtes,
> 1 à 2 min), en dehors de toute fenêtre, même celle du matin. `--force` est
> prévu pour ce genre de test manuel plafonné. Mais c'est à toi de décider si
> c'est acceptable devant l'équipe. **Recommandation : ne pas le faire** et s'en
> tenir au faux portail.

Si tu le fais malgré tout :
- Il écrit en **production** (`pmmp_veille`, compte `pmmp_app`). Ces 10
  consultations resteront en base, ce qui est sans danger (upsert, pas de
  doublon).
- **Plan B** si le site est lent ou indisponible : le circuit breaker arrête le
  run après 3 réponses lentes ou en erreur. Sinon, `Ctrl+C`. Dans les deux cas,
  enchaîner : « voilà le garde-fou en action », puis revenir au faux portail.

---

## 4. Les données : consultations et historique (15 min)

Dans **DataGrip** (connexion `pmmp_test`) ou en **psql** :

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d pmmp_test
```

```sql
-- Les 5 consultations réelles (arabe et français, dates au fuseau de Casablanca)
SELECT ref_consultation, left(objet, 60) AS objet, left(acheteur, 40) AS acheteur,
       to_char(date_limite_depot, 'DD/MM/YYYY HH24:MI') AS date_limite, statut, resultat
FROM consultations ORDER BY ref_consultation;

-- L'historique : ce que l'outil a détecté entre deux collectes
SELECT c.ref_consultation, h.type_evenement, h.champ,
       left(h.ancienne_valeur, 40) AS avant, left(h.nouvelle_valeur, 40) AS apres
FROM historique_modifications h JOIN consultations c ON c.id = h.consultation_id
ORDER BY c.ref_consultation, h.champ;

-- Le journal des collectes
SELECT id, demarre_le, statut, mode, force FROM collecte_runs ORDER BY id;
```

Attendu : 5 consultations, dont une `reporte` et une `annule`, et 5 lignes
d'historique :

| Type d'événement | Changement |
|---|---|
| `report_date` | Date limite + statut |
| `rectificatif` | Objet |
| `annulation` | Statut |
| `resultat` | Attributaire |

Dans `collecte_runs`, les 3 runs du test restent à `en_cours`, parce que le test
ne les clôture pas : c'est exactement la trace d'un run interrompu. Depuis le
25/09 après-midi, le run suivant lancé plus de 6 h après les passe en `echec`
(« interrompu »), voir PASSATION.md, point 3.

Montrer aussi le schéma commenté :

```powershell
Get-Content db\schema.sql | Select-Object -First 80
```

Pour quitter psql : `\q`.

**Plan B** si la base n'est pas disponible (mot de passe, service arrêté) :

```powershell
pytest tests/test_live_fixtures.py -v       # les 5 vraies pages sont lues correctement, sans base
Get-Content storage\test_items.jsonl -Encoding utf8 | Select-Object -First 2
```

`test_items.jsonl` contient les 5 consultations réelles extraites le 23/09, au
format JSON. On y voit les mêmes champs que dans la table. Ouvrir aussi une page
brute : `fixtures\live\detail\q9t__1038578.html`, dans le navigateur.

---

## 5. Le dépôt et le README (10 min)

```powershell
git log --oneline --graph -20
git ls-files | Select-String -NotMatch "^fixtures/|^tests/"
```

À parcourir dans `README.md` :

| Section | Contenu |
|---|---|
| §3–4 | Installation depuis zéro |
| §6 | Collecte par lots et reprise |
| §8 | Planification et supervision |
| §10 | Ce qu'il faut ajuster si le portail change (`parsers.py` uniquement) |

Au besoin, montrer `tests/` : une suite automatique de 109 tests (102 sans base,
les 7 autres demandent PostgreSQL). Chaque règle de collecte est protégée par un
test. Le bilan vérifié du 25/09 est dans `CHECKLIST.md`.

Pas de plan B nécessaire : tout est local.

---

## 6. Conclusion : PASSATION.md (10 min)

Ouvrir `PASSATION.md` et insister sur quatre points :

1. **Encadré « À régler en priorité »** : la tâche dépend du compte Windows du
   stagiaire. Il faut décider où l'outil tourne après le stage.
2. **Décision n° 1** : matin au lieu de nuit. C'est un écart volontaire à la
   consigne, à faire valider ou annuler par le chef de projet (une ligne dans
   `.env`).
3. **Ce qui reste à faire** : recherche, recherche sémantique, IA sur les DCE,
   interface Spring Boot + Angular, outils concurrents.
4. **Identifiants** : où ils se trouvent (`.env`, gestionnaire de mots de
   passe), le transfert du dépôt GitHub.

---

## Demain 26/09 après 06:00 — vérifier le premier vrai run

```powershell
Get-ScheduledTaskInfo -TaskName PMMP-Veille | Format-List LastRunTime, LastTaskResult   # 0 succès, 3 partiel, 1 échec, 2 refus
Get-ChildItem storage\logs | Sort-Object LastWriteTime | Select-Object -Last 1 | Get-Content -Tail 30
python -m pmmp_collector status
```

```sql
-- dans pmmp_veille (compte pmmp_app)
SELECT id, demarre_le, termine_le, statut, raison, nb_pages, nb_consultations FROM collecte_runs ORDER BY id DESC LIMIT 5;
SELECT count(*) FROM consultations;
```

Un premier run `partiel` (code 3, arrêt à 10:00) est **normal**, car la
collecte se fait par lots. Un `echec` (code 1) demande de lire le log.
