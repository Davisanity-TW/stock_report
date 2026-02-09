#!/usr/bin/env python3
"""Update the first markdown table inside a given daily section of a weekly TW report.

We use this for the 18:10 "insti refresh" pass:
- Keep the narrative (A/B/V/D/E) untouched
- Only replace the watchlist table (and optional gap note line) with the newly
  generated tmp/tw-table.md

Assumptions about the weekly report file:
- Daily section header starts with: "## YYYY-MM-DD"
- Inside that section, the first markdown table starts with a line beginning
  with "|" and continues while lines start with "|".
- After the table, there may be an optional 1-line gap note starting with
  "資料缺口註記："; if present immediately after the table (after optional blank
  line), it will be replaced together with the table.

This script is intentionally conservative: if it can't find a section/table,
it exits non-zero.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


HDR_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-file", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--table-file", required=True)
    args = ap.parse_args()

    week_path = Path(args.week_file)
    if not week_path.exists():
        raise SystemExit(f"week file not found: {week_path}")

    table_text = Path(args.table_file).read_text(encoding="utf-8").strip("\n")
    if not table_text.strip():
        raise SystemExit("table-file is empty")

    lines = week_path.read_text(encoding="utf-8").splitlines(True)

    # Find daily section start/end
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and re.match(rf"^##\s+{re.escape(args.date)}\b", ln):
            start = i
            break
    if start is None:
        raise SystemExit(f"daily header not found for date: {args.date}")

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if ln := lines[j]:
            if ln.startswith("## ") and HDR_RE.match(ln):
                end = j
                break

    section = lines[start:end]

    # Find first table in section
    t0 = None
    for k, ln in enumerate(section):
        if ln.lstrip().startswith("|"):
            t0 = k
            break
    if t0 is None:
        raise SystemExit("no markdown table found in daily section")

    t1 = t0
    while t1 < len(section) and section[t1].lstrip().startswith("|"):
        t1 += 1

    # Optionally consume a single gap note line right after the table
    # Skip at most one blank line
    t2 = t1
    if t2 < len(section) and section[t2].strip() == "":
        t2 += 1
    if t2 < len(section) and section[t2].startswith("資料缺口註記："):
        t2 += 1
        # keep following blank line if present (not required)

    before = section[:t0]
    after = section[t2:]

    new_block = []
    # Keep the existing header etc.
    new_block.extend(before)
    # Ensure exactly one blank line before table unless we're right after header
    if new_block and new_block[-1].strip() != "":
        new_block.append("\n")
    new_block.append(table_text + "\n")
    # Ensure a blank line after table
    if new_block and new_block[-1].strip() != "":
        new_block.append("\n")
    new_block.extend(after)

    out = lines[:start] + new_block + lines[end:]
    week_path.write_text("".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
