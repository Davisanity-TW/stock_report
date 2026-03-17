#!/usr/bin/env python3
"""Split a long text message into Telegram-safe chunks.

Designed for cron pipelines where upstream steps may fail.

Usage:
  python3 bin/split_telegram_message.py --in /tmp/finance_news_msg.txt --out /tmp/chunks.json \
    --max-chars 3500 --prefix-first "【財經新聞快報｜近5小時】\n"

Output format (JSON):
  {"count": N, "chunks": ["...", "..."]}

Rules:
- Normalizes newlines.
- Splits on blank-line boundaries first; falls back to hard split if a single block > max.
- Fails with non-zero exit if input missing/empty.
"""

from __future__ import annotations

import argparse
import json
import sys


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_blocks(text: str) -> list[str]:
    # Keep it simple: split on 2+ newlines.
    parts = []
    cur = []
    lines = text.split("\n")
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
        else:
            blank_run = 0
        cur.append(line)
        if blank_run >= 2:
            # finalize block
            block = "\n".join(cur).strip("\n")
            if block.strip():
                parts.append(block)
            cur = []
            blank_run = 0
    block = "\n".join(cur).strip("\n")
    if block.strip():
        parts.append(block)
    return parts


def hard_split(s: str, max_chars: int) -> list[str]:
    out = []
    while len(s) > max_chars:
        out.append(s[:max_chars])
        s = s[max_chars:]
    if s:
        out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--max-chars", type=int, default=3500)
    ap.add_argument("--prefix-first", default="")
    args = ap.parse_args()

    try:
        raw = open(args.in_path, "r", encoding="utf-8").read()
    except FileNotFoundError:
        print(f"ERROR: input file not found: {args.in_path}", file=sys.stderr)
        return 2

    text = normalize(raw).strip()
    if not text:
        print(f"ERROR: input file is empty: {args.in_path}", file=sys.stderr)
        return 3

    blocks = split_blocks(text)
    chunks: list[str] = []

    # If we prefix the first chunk, keep the final size <= max_chars
    first_max = args.max_chars - len(args.prefix_first) if args.prefix_first else args.max_chars
    if first_max <= 0:
        print("ERROR: prefix-first length exceeds max-chars", file=sys.stderr)
        return 4

    cur = ""
    cur_max = first_max

    for b in blocks:
        if not b.strip():
            continue
        cand = (cur + ("\n\n" if cur else "") + b)
        if len(cand) <= cur_max:
            cur = cand
        else:
            if cur:
                chunks.append(cur)
                cur = ""
                cur_max = args.max_chars  # after first chunk
            if len(b) <= cur_max:
                cur = b
            else:
                # single block too big → hard split
                chunks.extend(hard_split(b, cur_max))
                cur = ""
                cur_max = args.max_chars

    if cur:
        chunks.append(cur)

    if args.prefix_first:
        if chunks:
            chunks[0] = args.prefix_first + chunks[0]
        else:
            chunks = [args.prefix_first.rstrip("\n")]

    out = {"count": len(chunks), "chunks": chunks}
    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"OK: wrote {len(chunks)} chunks to {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
