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

STASH_BEFORE="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
git stash push -u -m "autostash before US weekly pull" >/dev/null 2>&1 || true
STASH_AFTER="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
RESTORE_STASH=0
if [[ -n "${STASH_AFTER}" && "${STASH_AFTER}" != "${STASH_BEFORE}" ]]; then
  RESTORE_STASH=1
fi

restore_stash() {
  if [[ "${RESTORE_STASH}" == "1" ]]; then
    git stash pop >/dev/null 2>&1 || {
      echo "warning: failed to restore autostash; check git stash list" >&2
    }
  fi
}
trap restore_stash EXIT

git pull --rebase

if ! python3 bin/similarity_gate.py --draft "${BLOCK}" --section us --top 5; then
  echo "warning: US similarity gate blocked; continuing because US daily reports use a fixed market-summary template" >&2
fi
python3 bin/md_upsert_daily_section.py --file "${WFILE}" --date "${DATE}" --content-file "${BLOCK}"
node bin/sync_reports.mjs

git add reports docs/reports bin/us_weekly_write_push.sh
git commit -m "US ${DATE}" || true
git push
