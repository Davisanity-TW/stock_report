#!/usr/bin/env python3
"""Upsert a daily section in a weekly markdown report.

We treat daily sections as:
  ## YYYY-MM-DD (Dow)
  ...content...

This script replaces the entire section body if the header already exists,
otherwise appends it at EOF.

Usage:
  md_upsert_daily_section.py --file path --date YYYY-MM-DD --content-file block.md

Notes:
- We match header by exact prefix: "## YYYY-MM-DD" (ignore the rest of the line).
- We preserve the existing header line if present; otherwise we use the header
  line from content-file's first line.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--content-file", required=True)
    args = ap.parse_args()

    fpath = Path(args.file)
    date = args.date
    block = Path(args.content_file).read_text(encoding="utf-8")
    if not block.strip():
        raise SystemExit("content-file is empty")

    lines = fpath.read_text(encoding="utf-8").splitlines(True) if fpath.exists() else []

    # Find existing header
    hdr_re = re.compile(rf"^##\s+{re.escape(date)}\b")
    next_hdr_re = re.compile(r"^##\s+\d{4}-\d{2}-\d{2}\b")

    start = None
    for i, ln in enumerate(lines):
        if hdr_re.match(ln):
            start = i
            break

    if start is None:
        # Append
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip() != "":
            lines.append("\n")
        lines.append(block if block.endswith("\n") else block + "\n")
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text("".join(lines), encoding="utf-8")
        return

    # Find end of section (start of next daily header or EOF)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if next_hdr_re.match(lines[j]):
            end = j
            break

    # Preserve existing header line, replace body with block body (skip first line of block)
    block_lines = block.splitlines(True)
    if not block_lines:
        raise SystemExit("content-file has no lines")

    new_section = [lines[start]]

    # Body from block, minus its first header line
    body = block_lines[1:]
    # Ensure there's at least one newline between header and body
    if body and not body[0].startswith("\n") and (len(body) == 0 or body[0].strip() != ""):
        pass
    new_section.extend(body)
    if new_section and not new_section[-1].endswith("\n"):
        new_section[-1] += "\n"

    out = lines[:start] + new_section
    # Ensure one blank line before next header (if next header exists and current doesn't end with blank)
    if end < len(lines):
        if out and out[-1].strip() != "":
            out.append("\n")
        out.extend(lines[end:])
    fpath.write_text("".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
