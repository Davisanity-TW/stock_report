#!/usr/bin/env python3
"""Ingest a Telegram-pasted YouTube summary into weekly markdown.

Usage:
  python3 bin/ingest_youtube_summary.py --date YYYY-MM-DD --title "..." --url "https://..." --infile /path/to/text
  cat text.txt | python3 bin/ingest_youtube_summary.py --date YYYY-MM-DD --stdin

Notes:
- Writes to reports/youtube/YYYY-Www.md (ISO week, Asia/Taipei)
- Appends entries (newer at bottom) by default.
"""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


def taipei_today() -> dt.date:
    if ZoneInfo is None:
        return dt.date.today()
    return dt.datetime.now(tz=ZoneInfo("Asia/Taipei")).date()


def iso_week_id(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def ensure_week_file(path: Path, week_id: str):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# YouTube 每週直播摘要 ({week_id})\n\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD; default Asia/Taipei today")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--infile", default=None)
    args = ap.parse_args()

    if args.date:
        d = dt.date.fromisoformat(args.date)
    else:
        d = taipei_today()

    week_id = iso_week_id(d)
    out = Path("reports/youtube") / f"{week_id}.md"
    ensure_week_file(out, week_id)

    if args.stdin:
        text = sys.stdin.read()
    elif args.infile:
        text = Path(args.infile).read_text(encoding="utf-8")
    else:
        raise SystemExit("Need --stdin or --infile")

    text = text.strip()
    if not text:
        raise SystemExit("Empty input")

    # Append as-is; caller is responsible for sending markdown-friendly text.
    # Keep chronological order: always append.
    dow = d.strftime('%a')
    block = f"## {d.isoformat()} ({dow})\n\n{text}\n\n"

    existing = out.read_text(encoding="utf-8")
    if not existing.endswith("\n"):
        existing += "\n"
    out.write_text(existing + block, encoding="utf-8")

    print(str(out))


if __name__ == "__main__":
    main()
