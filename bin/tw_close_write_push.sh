#!/usr/bin/env bash
set -euo pipefail

# One-shot TW close pipeline for cron:
# fetch close data, render summary/table, write weekly report, sync docs, push,
# then prepare Telegram-safe chunks from the same report content.

cd "$(dirname "$0")/.."

DAY="${1:-$(TZ=Asia/Taipei date +%F)}"
HM="$(TZ=Asia/Taipei date +%H:%M)"
CODES="${TW_CODES:-2330,0050,00631L,2454,2485,3481,2317,2308,8299,6669,2344,2327,2449,2357,3017,2408,2337,3491,6285,5388,8086,3105,4979,3163,3363,3234,3081,6442,3450,8261,5299,2481,5425}"
TMP_PREFIX="/tmp/tw-close-${DAY}-$$"

cleanup() {
  rm -f "${TMP_PREFIX}"*
}
trap cleanup EXIT

if [[ ! "${DAY}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: bad DAY: ${DAY}" >&2
  exit 2
fi

mkdir -p tmp reports/tw

python3 - <<PY
import json
import urllib.request

url = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json"
try:
    data = json.loads(urllib.request.urlopen(url, timeout=20).read().decode("utf-8"))
    out = {"ok": True, "source": url, "payload": data}
except Exception as e:
    out = {"ok": False, "source": url, "error": str(e)}

with open("${TMP_PREFIX}-index.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
PY
test -s "${TMP_PREFIX}-index.json"
mv "${TMP_PREFIX}-index.json" tmp/tw-index.json

python3 bin/tw_report_data.py --date "${DAY}" --codes "${CODES}" > "${TMP_PREFIX}-data.json"
test -s "${TMP_PREFIX}-data.json"
mv "${TMP_PREFIX}-data.json" tmp/tw-data.json

python3 bin/tw_make_table.py tmp/tw-data.json > "${TMP_PREFIX}-table.md"
test -s "${TMP_PREFIX}-table.md"
mv "${TMP_PREFIX}-table.md" tmp/tw-table.md

python3 bin/finance_news_collect.py --window-hours 10 > "${TMP_PREFIX}-news.json"
test -s "${TMP_PREFIX}-news.json"
mv "${TMP_PREFIX}-news.json" tmp/tw_news_raw.json

python3 bin/tw_make_summary.py \
  --date "${DAY}" \
  --index tmp/tw-index.json \
  --data tmp/tw-data.json \
  --news tmp/tw_news_raw.json \
  --out "${TMP_PREFIX}-summary.md"
test -s "${TMP_PREFIX}-summary.md"
mv "${TMP_PREFIX}-summary.md" tmp/tw-summary.md

python3 bin/tw_md_add_names.py --in tmp/tw-summary.md --out "${TMP_PREFIX}-summary-named.md"
test -s "${TMP_PREFIX}-summary-named.md"
mv "${TMP_PREFIX}-summary-named.md" tmp/tw-summary-named.md

{
  cat tmp/tw-summary-named.md
  echo
  echo "#### 追蹤清單（收盤）"
  echo
  cat tmp/tw-table.md
  echo
} > "${TMP_PREFIX}-daily-block.md"
test -s "${TMP_PREFIX}-daily-block.md"
mv "${TMP_PREFIX}-daily-block.md" tmp/tw-daily-block.md

{
  echo "【台股收盤報告｜${DAY} ${HM}】"
  echo
  cat tmp/tw-daily-block.md
} > "${TMP_PREFIX}-telegram.md"
python3 bin/tw_md_add_names.py --in "${TMP_PREFIX}-telegram.md" --out tmp/tw-latest-named.md
cp tmp/tw-latest-named.md tmp/tw-latest.md
echo "${DAY}" > tmp/tw-latest-date.txt

WEEK="$(python3 - <<PY
import datetime as dt
iso = dt.date.fromisoformat("${DAY}").isocalendar()
print(f"{iso.year}-W{iso.week:02d}")
PY
)"
WFILE="reports/tw/${WEEK}.md"

export GIT_TERMINAL_PROMPT=0

STASH_BEFORE="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
git stash push -u -m "autostash before TW close pull" >/dev/null 2>&1 || true
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
trap 'cleanup; restore_stash' EXIT

git pull --rebase

python3 bin/md_upsert_daily_section.py --file "${WFILE}" --date "${DAY}" --content-file tmp/tw-daily-block.md
node bin/sync_reports.mjs

git add reports docs/reports
if git diff --cached --quiet; then
  echo "OK: no stock_report changes for ${DAY}"
else
  git commit -m "TW close report ${DAY}"
  git push
fi

python3 bin/split_telegram_message.py \
  --in tmp/tw-latest-named.md \
  --out tmp/tw-telegram-chunks.json \
  --max-chars 3500
python3 bin/json_chunks_to_files.py \
  --in tmp/tw-telegram-chunks.json \
  --out-pattern /tmp/tw_close_chunk_%02d.txt \
  --count-file /tmp/tw_close_chunk_count.txt

echo "OK: TW close report done for ${DAY}; telegram chunks: $(cat /tmp/tw_close_chunk_count.txt)"
