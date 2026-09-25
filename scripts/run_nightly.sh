#!/usr/bin/env bash
# Lancement quotidien planifié du collecteur PMMP (cron, Linux).
# Nom historique : depuis le 25/09/2026 la collecte tourne le MATIN
# (PMMP_ALLOWED_WINDOW=06:00-10:00, choix du stagiaire, différent de la consigne
# d'origine du chef de projet : nuit 23:00-06:00).
# Exemple de crontab pour un serveur à l'heure de Casablanca (la fenêtre est de
# toute façon vérifiée par le collecteur dans le fuseau Africa/Casablanca) :
#   0 6 * * *  /opt/pmmp_collector/scripts/run_nightly.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/storage/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.venv/bin/activate"

# flock : jamais deux runs en parallèle (une seule requête à la fois vers le portail).
set +e
flock -n "$PROJECT_DIR/storage/.run.lock" python -m pmmp_collector crawl >>"$LOG_FILE" 2>&1
CODE=$?
set -e

case $CODE in
  0) echo "$(date -Is) succès" >>"$LOG_FILE" ;;
  1) echo "$(date -Is) ÉCHEC (voir ce log et storage/last_run.json)" >>"$LOG_FILE" ;;
  2) echo "$(date -Is) refusé : hors fenêtre horaire" >>"$LOG_FILE" ;;
  3) echo "$(date -Is) partiel : fenêtre horaire terminée avant la fin" >>"$LOG_FILE" ;;
  *) echo "$(date -Is) code inattendu $CODE (run déjà en cours ?)" >>"$LOG_FILE" ;;
esac

# Nettoyage des logs de plus de 60 jours
find "$LOG_DIR" -name 'run_*.log' -mtime +60 -delete
exit $CODE
