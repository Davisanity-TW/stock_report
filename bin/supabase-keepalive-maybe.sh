#!/usr/bin/env bash
set -euo pipefail

# Run daily; only actually ping Supabase if last successful ping was >= 6 days ago.

STATE_FILE="/home/ubuntu/clawd/secrets/supabase_keepalive_last_success_epoch"
NOW="$(date +%s)"
INTERVAL_SEC=$((6*24*60*60))

LAST=0
if [[ -f "$STATE_FILE" ]]; then
  LAST="$(tr -d '\n' < "$STATE_FILE" || echo 0)"
  [[ "$LAST" =~ ^[0-9]+$ ]] || LAST=0
fi

AGE=$((NOW - LAST))
if (( AGE < INTERVAL_SEC )); then
  echo "SKIP: last ping ${AGE}s ago (< ${INTERVAL_SEC}s)"
  exit 0
fi

# Ping
"/home/ubuntu/clawd/stock_report/bin/supabase-keepalive.sh"

echo "$NOW" > "$STATE_FILE"
