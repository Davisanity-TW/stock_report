#!/usr/bin/env bash
set -euo pipefail

# Write/Upsert latest US daily block into the ISO-week report and push.
# Kept as a script so cron does not depend on GNU date flags or multiline shell.

cd "$(dirname "$0")/.."

DATE="${1:-}"
if [[ -z "${DATE}" ]]; then
  DATE="$(cat tmp/us-latest-date.txt 2>/dev/null || TZ=Asia/Taipei date +%F)"
fi

if [[ -z "${DATE}" ]]; then
  echo "missing DATE (pass YYYY-MM-DD)" >&2
  exit 2
fi

if [[ ! -s tmp/us-latest.md ]]; then
  echo "missing tmp/us-latest.md (run US close prep first)" >&2
  exit 2
fi

WEEK="$(python3 - "${DATE}" <<'PY'
import datetime as dt
import sys

d = dt.date.fromisoformat(sys.argv[1])
iso = d.isocalendar()
print(f"{iso.year}-W{iso.week:02d}")
PY
)"
WFILE="reports/us/${WEEK}.md"
BLOCK="/tmp/us-daily-block-${DATE}.md"
cp tmp/us-latest.md "${BLOCK}"

export GIT_TERMINAL_PROMPT=0

git stash push -u -m "autostash before US weekly pull" >/dev/null 2>&1 || true
git pull --rebase

python3 bin/similarity_gate.py --draft "${BLOCK}" --section us --top 5
python3 bin/md_upsert_daily_section.py --file "${WFILE}" --date "${DATE}" --content-file "${BLOCK}"
node bin/sync_reports.mjs

git add reports docs/reports bin/us_weekly_write_push.sh
git commit -m "US ${DATE}" || true
git push
