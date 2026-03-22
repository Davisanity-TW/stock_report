#!/usr/bin/env python3
"""Convert a chunks JSON (from split_telegram_message.py) into numbered text files.

Input JSON format:
  {"count": N, "chunks": ["...", "..."]}

Usage:
  python3 bin/json_chunks_to_files.py --in /tmp/chunks.json \
    --out-pattern /tmp/chunk_%02d.txt --count-file /tmp/chunk_count.txt

Notes:
- Files are numbered starting at 1, so %02d -> 01, 02, ...
- Writes N (with trailing newline) to --count-file.
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out-pattern", required=True)
    ap.add_argument("--count-file", required=True)
    args = ap.parse_args()

    try:
        data = json.load(open(args.in_path, "r", encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: input file not found: {args.in_path}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: failed to parse JSON: {args.in_path}: {e}", file=sys.stderr)
        return 3

    chunks = data.get("chunks")
    if not isinstance(chunks, list) or not all(isinstance(x, str) for x in chunks):
        print("ERROR: invalid JSON format: expected {count:int, chunks:[str,...]}", file=sys.stderr)
        return 4

    n = len(chunks)
    try:
        for i, text in enumerate(chunks, start=1):
            out_path = args.out_pattern % i
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
        with open(args.count_file, "w", encoding="utf-8") as f:
            f.write(str(n) + "\n")
    except TypeError as e:
        print(f"ERROR: out-pattern formatting failed (pattern={args.out_pattern}): {e}", file=sys.stderr)
        return 5

    print(f"OK: wrote {n} chunk files and count-file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
