#!/usr/bin/env python3
"""Generate CCStockWorkEnv-style markdown reports and publish into stock_report site.

This is a lightweight integration: we reuse CCStockWorkEnv's python modules
(vendored under external/ccstockworkenv/tool_scripts) and write output into
this repo's reports/ccstock folder, which is published via VitePress.

Usage examples:
  ./.venv_ccstock/bin/python bin/ccstock_generate_report.py --ticker 2330 --market TW
  ./.venv_ccstock/bin/python bin/ccstock_generate_report.py --ticker AAPL --market US

Outputs:
  reports/ccstock/YYYY-Www.md (upsert daily section)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CCROOT = ROOT / "external" / "ccstockworkenv" / "tool_scripts"

# Make CCStockWorkEnv modules importable
sys.path.insert(0, str(CCROOT / "report_gen"))
sys.path.insert(0, str(CCROOT / "market_data"))
sys.path.insert(0, str(CCROOT / "financial_calc"))

from markdown_report import generate_single_report  # type: ignore


def iso_week_file(day: dt.date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}.md"


def upsert_daily_section(weekly_path: Path, day: dt.date, content_md: str) -> None:
    """Upsert section starting with `## YYYY-MM-DD` until next such header."""

    date_str = day.isoformat()
    header_prefix = f"## {date_str}"

    if not weekly_path.exists():
        weekly_path.parent.mkdir(parents=True, exist_ok=True)
        weekly_path.write_text(f"# CCStockWorkEnv Reports ({iso_week_file(day).replace('.md','')})\n\n", encoding="utf-8")

    lines = weekly_path.read_text(encoding="utf-8").splitlines(True)

    def is_hdr(ln: str) -> bool:
        return ln.startswith("## ") and len(ln) >= 13 and ln[3:13].count("-") == 2

    # Find existing
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(header_prefix):
            start = i
            break

    block = content_md
    if not block.endswith("\n"):
        block += "\n"

    block_lines = block.splitlines(True)
    if not block_lines or not block_lines[0].startswith("## "):
        raise SystemExit("content must start with a '## YYYY-MM-DD ...' header")

    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("\n")
        lines.append(block)
        weekly_path.write_text("".join(lines), encoding="utf-8")
        return

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if is_hdr(lines[j]):
            end = j
            break

    # preserve existing header line, replace body
    new_section = [lines[start]] + block_lines[1:]
    if new_section and not new_section[-1].endswith("\n"):
        new_section[-1] += "\n"

    out = lines[:start] + new_section
    if end < len(lines):
        if out and out[-1].strip() != "":
            out.append("\n")
        out.extend(lines[end:])

    weekly_path.write_text("".join(out), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--market", required=True, choices=["TW", "US", "CN"])
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today Asia/Taipei)")
    args = ap.parse_args()

    # Date based on Asia/Taipei for report filing
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Taipei")
        day = dt.datetime.now(tz).date() if not args.date else dt.date.fromisoformat(args.date)
    except Exception:
        day = dt.date.today() if not args.date else dt.date.fromisoformat(args.date)

    # Generate single report markdown into temp
    out_dir = ROOT / "tmp" / "ccstock"
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = generate_single_report(args.ticker, args.market, str(out_dir))
    md = Path(report_path).read_text(encoding="utf-8")

    # Wrap as daily section. Keep report title as subheading to avoid breaking weekly structure.
    header = f"## {day.isoformat()} ({day.strftime('%a')})\n\n"
    # Demote the first markdown heading ("# ...") to "### ..." so it stays within the daily section.
    md_lines = md.splitlines(True)
    if md_lines and md_lines[0].startswith("# "):
        md_lines[0] = "### " + md_lines[0][2:]
    block = header + "".join(md_lines)

    weekly = ROOT / "reports" / "ccstock" / iso_week_file(day)
    upsert_daily_section(weekly, day, block)

    print(str(weekly))


if __name__ == "__main__":
    main()
