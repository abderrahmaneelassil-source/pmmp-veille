# Passation — moteur de veille PMMP (pmmp_veille)

Note de fin de stage, 25/09/2026. Elle s'adresse à l'équipe qui reprend le projet
sans l'avoir suivi. Pour le détail technique : `README.md` (installation,
utilisation), `AUDIT.md` (rapport d'audit du 24/09 et mise à jour du 25/09) et
`CHECKLIST.md` (vérification complète du 25/09 après-midi).

**Personne responsable : Abderrahmane Elassil (stagiaire), jusqu'au 25/09/2026.
Après cette date, il n'y a plus de responsable : l'équipe doit en désigner un**
(qui surveille les runs, reçoit les questions sur l'outil et tranche les points
ouverts).

---

## En deux minutes

**Ce que fait l'outil.** Chaque jour, un programme consulte le Portail Marocain
des Marchés Publics (marchespublics.gov.ma). Il relève les appels d'offres
publiés et télécharge leurs dossiers de consultation (DCE). Il range le tout
dans une base de données. Il garde aussi l'historique des changements :
report de date, rectificatif, annulation, résultat.

**Où on en est.**

| | État |
|---|---|
| Collecteur, base de données, tests automatiques | Terminés, audités (24/09) et revérifiés (25/09, `CHECKLIST.md`). Tous les tests passent, y compris ceux qui demandent PostgreSQL (lancés sur une base jetable). |
| Lancement automatique chaque matin à 06:00 | Programmé sur le PC de développement. **Premier lancement réel : 26/09/2026 à 06:00**, donc après la fin du stage. |
| Collecte réelle sur le portail | **Pas encore faite à grande échelle.** Seule une petite capture (1 page, 5 consultations) a été faite le 23/09. Elle sert de jeu de test. |
| Base `pmmp_veille` | **Vide à ce jour** (0 consultation). C'est normal : elle a été vidée après l'audit. Elle se remplira au premier run. |

> ⚠️ **À régler en priorité : le lancement automatique dépend du compte Windows
> du stagiaire.** La tâche `PMMP-Veille` tourne sous le compte `abder_r9rl0a3`
> du PC de développement, et **seulement si sa session est ouverte** (même
> verrouillée). Sans session ouverte ou avec le PC éteint, il n'y a pas de
> collecte, sans aucun message d'erreur. Il faut décider rapidement où l'outil
> tournera durablement : un serveur, ou un PC d'équipe avec un compte de
> service. La procédure est dans le README, §8.

---

## Décisions prises pendant le stage qui diffèrent du cadrage initial

### 1. Collecte le matin au lieu de la nuit — écart volontaire à la consigne

- **Consigne d'origine du chef de projet** : collecter « la nuit ou en heures
  creuses uniquement » (23:00–06:00). Elle était présentée comme non négociable.
- **Ce qui est en place** : collecte **le matin, de 06:00 à 10:00** (heure de
  Casablanca).
- **Qui l'a décidé** : le stagiaire, le 25/09/2026. **C'est un choix, pas une
  correction technique.** Le chef de projet ne l'a pas validé à ce jour.
- **Conséquence à connaître** : de 08:00 à 10:00, la collecte tourne en même
  temps que les utilisateurs humains du portail en début de journée. C'est
  justement ce que la consigne d'origine voulait éviter. La collecte reste lente
  et polie : une seule requête à la fois, au moins 3 secondes entre deux
  requêtes, et arrêt automatique si le site ralentit.
- **Pour revenir à la nuit**, il suffit de changer une ligne dans le fichier de
  configuration `.env` : `PMMP_ALLOWED_WINDOW=23:00-06:00`. Il faut ensuite
  décaler l'heure de la tâche planifiée à 23:00 (README §8). Aucune ligne de code
  à modifier.

### 2. Collecte par lots, étalée sur plusieurs semaines

Le portail contient environ **100 000 consultations**. Aux règles de politesse
imposées, il est impossible de tout lire en une seule séance. Chaque matin,
l'outil lit donc au plus **1 200 fiches** : les nouvelles, celles qui ont changé
et celles qui avaient échoué la veille. Il s'arrête ensuite et reprend le
lendemain.

- Première collecte complète : **plusieurs semaines** (≈ 80 jours à 1 200 par
  jour). Ensuite, chaque matin ne traite que les nouveautés.
- Le réglage est dans `.env` : `PMMP_MAX_ITEMS=1200`. Il a été baissé de 2 000 à
  1 200 le 25/09, pour que la séance tienne dans les 4 h du matin. Le fichier
  modèle `.env.example` indique encore 2 000 (voir « Ce qui reste à faire »).

### 3. Reprise sans numéro de page mémorisé

Le 25/09, un « marque-page » avait été demandé : noter la dernière page lue pour
reprendre au même endroit le lendemain. **Ce n'est pas ce qui a été fait.**
C'est la base de données elle-même qui sert de point de reprise. Chaque matin,
l'outil repart de la première page et saute sans rien télécharger tout ce qu'il
connaît déjà. Raison : de nouvelles publications arrivent chaque jour et décalent
les pages. Un numéro de page mémorisé ferait sauter ou relire des consultations.

### 4. Sécurité de la base : un compte dédié à l'application

L'application ne se connecte plus avec le compte propriétaire de la base. Elle
utilise un compte **`pmmp_app`** aux droits limités : il peut lire, ajouter et
modifier, mais pas supprimer, vider ou modifier la structure. L'ancien compte
`pmmp` ne peut plus se connecter. **Effet de bord** : l'accès « tout le monde »
a été retiré sur les **autres** bases du même serveur PostgreSQL (voir « Points
à surveiller », n° 8).

### 5. Dossiers de consultation derrière un formulaire : non soumis

Certains DCE ne sont accessibles qu'après un formulaire : identification ou
acceptation de conditions d'utilisation. L'outil **ne remplit pas** ces
formulaires. Il archive la page et marque le DCE `page_intermediaire`. Accepter
des conditions au nom de TACHFIR est **une décision du chef de projet**, qui
reste à prendre.

---

## Points à surveiller

Reformulés depuis la section « Points à surveiller » d'`AUDIT.md`, avec la
gravité de chaque point.

| # | Le point | Ce que ça veut dire concrètement | Gravité |
|---|---|---|---|
| 1 | **Taille du site : plus de 10 000 pages** | En affichage standard, la liste du portail fait plus de 10 000 pages. L'outil l'affiche à 100 résultats par page, soit environ 1 000 pages. C'est encore trop pour une seule séance : la collecte est donc découpée en lots quotidiens (décision n° 2). **Un run qui s'arrête à 10:00 avant d'avoir tout vu est normal** (statut `partiel`). Tant qu'aucun run n'a fini en `succes`, les consultations expirées ne sont pas marquées « clôturées » et l'alerte « aucun succès depuis 26 h » se déclenche. | Moyenne : à vérifier sur les premiers jours |
| 2 | **Nom de l'acheteur et lieu d'exécution : la liste et la fiche ne disent pas la même chose** | Le portail écrit l'acheteur différemment sur la liste et sur la fiche détaillée (« LE DIRECTEUR PROVINCIAL… » contre « M3 / DPESK - LE DIRECTEUR… »). Si la fiche ne peut pas être lue un jour, l'outil garde la version de la liste. L'historique enregistre alors un faux « rectificatif », annulé le lendemain. | Faible : bruit dans l'historique |
| 3 | **Run interrompu qui reste « en cours »** | Si le PC s'éteint ou si le programme est tué pendant une collecte, la ligne du journal (`collecte_runs`) reste à `en_cours`. **Corrigé le 25/09** : au lancement suivant, un run `en_cours` depuis plus de 6 h (`PMMP_STALE_RUN_HOURS`) passe en `echec` avec la raison `interrompu : …`, et un message `ATTENTION` apparaît dans le log. Pendant les 6 premières heures, la ligne reste `en_cours`. | Faible : à savoir lire |
| 4 | **Collation Windows de la base** | La base du PC de développement trie le texte selon les règles de Windows (`English_United States.1252`). Les textes arabes sont stockés correctement. Seul **l'ordre de tri** peut surprendre. Sur un serveur Linux, créer la base avec une locale UTF-8. | Faible |
| 5 | **Fuseau horaire (`tzdata`)** | L'heure du Maroc est calculée à partir d'une bibliothèque qui suit les changements d'heure officiels (`tzdata`). Le Maroc change parfois ses règles, par exemple pendant le Ramadan. Il faut garder cette bibliothèque à jour (`pip install -U tzdata`), sinon les heures et la fenêtre de collecte peuvent être décalées d'une heure. | Moyenne : à faire régulièrement |
| 6 | **`reservation_pme` toujours vide** | L'information « marché réservé aux PME » n'apparaît sur aucune des pages réelles examinées : la colonne est vide partout. La date de publication ne vient que de la liste, pas de la fiche. Un filtre « réservé PME » ne marchera pas tant qu'on n'a pas trouvé où le portail affiche cette information. | Moyenne pour les futures fonctions de recherche |
| 7 | **Script de lancement Linux jamais exécuté** | Le script prévu pour un serveur Linux (`scripts/run_nightly.sh`) a été relu, mais **jamais lancé pour de vrai** : le développement s'est fait sous Windows. Il faudra le tester lors de l'installation sur serveur et vérifier que l'outil `flock` y est présent. | Moyenne le jour de la migration |
| 8 | **Accès retiré sur les autres bases du serveur** | En sécurisant le compte de l'application, l'accès « tout le monde » a été retiré sur **toutes les autres bases** du même serveur PostgreSQL. Sur le PC de développement, ça n'a aucun effet. Sur un serveur **partagé** avec d'autres projets, ça pourrait bloquer d'autres applications : **prévenir l'administrateur avant** d'appliquer `db/roles.sql` (README §4.4). | Élevée sur un serveur partagé |
| 9 | **Premier vrai run : 26/09 à 06:00** | Aucune collecte complète n'a encore tourné sur le vrai portail. Le premier lancement automatique est le vrai test. À regarder le 26/09 au matin : `storage/logs/`, `storage/last_run.json`, et `SELECT * FROM collecte_runs` (commandes dans `DEMO.md`). | Élevée : à vérifier dès le 26/09 |

---

## Ce qui reste à faire

Repris de la liste « transmis à l'équipe » de la feuille de route d'origine.
**Retiré de la liste : la migration vers Scrapy.** Elle est faite : c'est le
collecteur actuel.

| Chantier | Commentaire |
|---|---|
| **Recherche plein texte + filtres + alertes email** | La base contient déjà les champs utiles : objet (arabe et français), acheteur, catégorie, date limite, statut. Attention au filtre « réservé PME », voir le point 6. |
| **Recherche sémantique** | Pas commencée. |
| **Analyse par IA des DCE** | Les DCE sont stockés comme fichiers sur disque (`storage/dce/`), leur chemin est en base. Voir aussi la décision n° 5 : les DCE derrière un formulaire ne sont pas téléchargés. |
| **Interface complète (Spring Boot + Angular)** | Pas commencée. Elle lira la base PostgreSQL existante (schéma documenté dans `db/schema.sql`) avec le compte `pmmp_app` ou un compte en lecture seule à créer. |
| **Test des outils concurrents** | Pas commencé. |

Petites tâches de consolidation, issues de ce stage :

- **Décider où tourne la collecte** après le stage : serveur, ou compte de
  service. Voir l'encadré en tête.
- **Faire valider (ou annuler) l'horaire du matin** par le chef de projet.
  Décision n° 1.
- Vérifier les premiers runs réels (point 9). Ajuster `PMMP_MAX_ITEMS` si les
  runs finissent en `partiel`.
- ~~Aligner `.env.example` sur `PMMP_MAX_ITEMS=1200`~~ : fait le 25/09.
- ~~Lancer les tests qui demandent PostgreSQL~~ : faits le 25/09 sur une base
  jetable, tous verts (voir `CHECKLIST.md`).

Manques identifiés le 25/09 (détail et raisons dans `CHECKLIST.md`) :

- **Aucune alerte en cas d'échec** (email, Teams…). Aujourd'hui, il faut aller
  lire les logs ou `collecte_runs`. C'est le manque le plus important.
- **Aucune sauvegarde automatique de la base.** La commande manuelle a été testée
  (voir « Sauvegarde de la base » ci-dessous). Il reste à la planifier.
- **Un DCE rectifié sur le portail n'est jamais retéléchargé** : dès qu'un DCE
  est sur le disque, l'outil le considère `deja_present`.
- **Le HTML brut s'accumule sans purge** dans `storage/raw_html/` : chaque run
  réarchive toutes les pages de liste lues. Il faut décider d'une durée de
  conservation.
- **Collecte le week-end et les jours fériés** : question ouverte, non tranchée
  (aujourd'hui : tous les jours).
- **Le dépôt GitHub est public** (vérifié le 25/09) : il ne contient aucun
  secret, mais il décrit l'infrastructure. Le passer en privé si ce n'est pas voulu.

---

## Identifiants et accès à transmettre

**Aucun mot de passe n'est écrit dans ce document ni dans le dépôt Git.** Le
tableau dit où chacun se trouve, pas sa valeur.

| Accès | À quoi il sert | Où se trouve le secret | Action à la passation |
|---|---|---|---|
| Compte PostgreSQL **`pmmp_app`** (base `pmmp_veille`, `localhost:5432`) | Compte utilisé par le collecteur | Fichier **`.env`** à la racine du projet, sur le PC de développement (ligne `PMMP_DATABASE_URL`). Ce fichier n'est pas dans Git. | Le copier dans le gestionnaire de mots de passe de l'équipe. Si possible, le changer ensuite (`db/roles.sql`). |
| Compte PostgreSQL **`postgres`** (superutilisateur) | Administration du serveur, base de test `pmmp_test` | Connu du stagiaire uniquement. Changé après l'audit. | Le transmettre via le gestionnaire de mots de passe, puis le changer. |
| Compte PostgreSQL **`pmmp`** | Propriétaire des tables | Aucun : il ne peut pas se connecter (volontaire) | Rien |
| **Dépôt GitHub** `abderrahmaneelassil-source/pmmp-veille` | Code source | Compte GitHub **personnel** du stagiaire | Transférer le dépôt vers l'organisation TACHFIR, ou ajouter l'équipe comme administrateur. |
| **Tâche planifiée Windows** `PMMP-Veille` | Lancement quotidien à 06:00 | Compte Windows `abder_r9rl0a3` du PC de développement (aucun mot de passe enregistré dans la tâche) | Recréer la tâche sous un compte d'équipe (commande en tête de `scripts/run_nightly.ps1`). |
| Adresse de contact **sales@tachfir.com** | Écrite dans l'identifiant du collecteur (User-Agent). C'est elle que l'administrateur du portail utilisera s'il veut nous joindre. | — | S'assurer que quelqu'un lit cette boîte et sait de quoi il s'agit. |
| Connexion **DataGrip** | Consulter les données | Configurée localement sur le PC de développement | Utiliser `pmmp_app` (consultation) ou `postgres` (administration). L'ancien compte `pmmp` ne marche plus. |

---

## Exploitation : arrêter, relancer, revenir en arrière, sauvegarder

Toutes les commandes sont en PowerShell, à lancer depuis le dossier du projet avec
le venv activé (`.venv\Scripts\Activate.ps1`).

### Arrêter le bot

```powershell
# 1. Empêcher les prochains lancements automatiques (réversible)
Disable-ScheduledTask -TaskName "PMMP-Veille"
# 2. Arrêter un run lancé par la tâche planifiée
Stop-ScheduledTask -TaskName "PMMP-Veille"
#    (non vérifié : le python.exe lancé par la tâche peut survivre à cet arrêt ;
#     contrôler avec l'étape 3 qu'il ne reste aucun processus)
# 3. Arrêter un run lancé à la main : Ctrl+C dans sa fenêtre (une seule fois = arrêt propre).
#    Sinon, retrouver le processus puis l'arrêter :
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object CommandLine -like "*pmmp_collector crawl*" | Select-Object ProcessId, CommandLine
Stop-Process -Id <ProcessId>
```

Un run arrêté brutalement (étape 2, ou étape 3 sans Ctrl+C) laisse sa ligne
`collecte_runs` à `en_cours`. Elle passera en `echec` (« interrompu ») au premier
run lancé plus de 6 h après. Le verrou « un seul run à la fois » se libère tout
seul : il n'y a aucun fichier à supprimer.

### Relancer

```powershell
Enable-ScheduledTask -TaskName "PMMP-Veille"      # réactive le lancement de 06:00
python -m pmmp_collector status                    # fenêtre ouverte ? dernier run ?
python -m pmmp_collector crawl --force             # test manuel plafonné (1 page, 10 fiches), à toute heure
Start-ScheduledTask -TaskName "PMMP-Veille"        # comme à 06:00 (refusé hors fenêtre, code 2)
```

Si un run tourne déjà, le second est refusé (code `4`, « un autre run du
collecteur est déjà en cours »). C'est normal : il suffit d'attendre la fin du premier.

### Revenir à une version précédente (régression)

La tâche exécute **le code de la branche Git extraite** dans le dossier du projet.

```powershell
git log --oneline -15                      # repérer le dernier commit sain
git revert <commit_fautif>                 # annule un commit en gardant l'historique (à préférer)
# ou, en urgence, revenir temporairement à un état antérieur :
git switch --detach <commit_sain>          # pour revenir ensuite : git switch <branche>
pip install -r requirements.txt            # si requirements.txt a changé entre les deux
pytest                                     # vérifier avant la prochaine collecte
```

Revenir en arrière dans le code **ne remet pas la base de données** dans son état
précédent : pour ça, il faut une sauvegarde (ci-dessous). Les changements du 25/09
n'ont pas modifié le schéma de la base.

### Sauvegarde de la base

**Il n'existe aujourd'hui aucune sauvegarde automatique de `pmmp_veille`.** C'est
un vrai manque : avec un disque perdu ou une mauvaise manipulation, tout
l'historique des modifications disparaît. La commande ci-dessous a été **testée le
25/09** : sauvegarde avec `pmmp_app`, puis restauration réussie dans une base de test.

```powershell
# Sauvegarde (demande le mot de passe de pmmp_app, voir .env)
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -h localhost -U pmmp_app -d pmmp_veille -Fc --no-owner -f "pmmp_veille_$(Get-Date -Format yyyyMMdd).dump"
# Restauration dans une base VIDE créée au préalable (superutilisateur)
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -h localhost -U postgres -d <base_vide> --no-owner <fichier>.dump
```

À faire : planifier cette sauvegarde (par exemple chaque jour après 10:00) et
copier les fichiers **ailleurs que sur ce PC**. Les DCE (`storage/dce/`) sont de
simples fichiers : à inclure dans la sauvegarde du disque.

### Erreurs fréquentes

| Message ou symptôme | Cause | Que faire |
|---|---|---|
| `REFUS : il est … hors de la fenêtre autorisée` (code 2) | Lancement en dehors de 06:00–10:00 | Normal. Pour un test : `--force`. |
| `REFUS : un autre run du collecteur est déjà en cours` (code 4) | Un run tourne déjà (tâche planifiée ou autre fenêtre) | Attendre sa fin. |
| `ÉCHEC avant démarrage … connexion PostgreSQL impossible` (code 1) | PostgreSQL arrêté, mot de passe changé ou `.env` absent | Démarrer le service PostgreSQL, vérifier `PMMP_DATABASE_URL`. |
| `CIRCUIT BREAKER DÉCLENCHÉ` (code 1) | Le portail a répondu en erreur ou trop lentement 3 fois de suite | Ne rien forcer : ça repartira le lendemain. Si ça dure, regarder le portail à la main. |
| Statut `partiel` (code 3) | La fenêtre s'est fermée à 10:00 avant la fin du lot | Normal au début. Si ça arrive tous les jours, baisser `PMMP_MAX_ITEMS`. |
| Statut `echec`, raison `aucune_consultation_extraite` | Le portail a changé son HTML | Voir README §10 : ajuster `parsers.py`. |
| `ATTENTION : le run n°… ne s'est jamais terminé` | Un run précédent a été tué (PC éteint…) | Pour information : la ligne est passée en `echec`. |
| Aucun log dans `storage/logs/` un matin | PC éteint, en veille ou session fermée à 06:00 | Voir l'encadré en tête. |

Tableau complet des erreurs de base de données : README §4.

---

## Où trouver quoi

| Besoin | Fichier |
|---|---|
| Installer, configurer, lancer | `README.md` |
| Pourquoi les règles de collecte existent | `README.md` §1 |
| Structure de la base | `db/schema.sql` (commenté) |
| Réglages (horaire, taille des lots, pause…) | `.env` (modèle : `.env.example`) |
| Si le portail change son HTML | `src/pmmp_collector/parsers.py` (seul fichier à ajuster), README §10 |
| Rapport technique d'audit | `AUDIT.md` |
| Déroulé de la démo du 25/09 | `DEMO.md` |
| Vérification complète du 25/09 (checklist) | `CHECKLIST.md` |
| Code source | `src/pmmp_collector/`. Dossier du projet sur le PC de développement : `C:\Users\abder_r9rl0a3\pmmp_collector` |
| Dépendances | `requirements.txt` (repris dans `pyproject.toml`). Python 3.11 ou plus (version utilisée : 3.14.5) |
