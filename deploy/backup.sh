#!/usr/bin/env bash
# Daily cron example: 0 3 * * * /opt/PubQuizStats/deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
sqlite3 data/quiz_results.db ".backup 'backups/quiz_results_$(date +%F).db'"
find backups -name 'quiz_results_*.db' -mtime +30 -delete
