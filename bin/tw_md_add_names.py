#!/usr/bin/env python3
"""Post-process TW report markdown to ensure stock codes are accompanied by names.

We insert "<code> <name>" for bare codes found in narrative parts, using the
same NAME_MAP as tw_make_table.py.

This is intended for Telegram-friendly summaries where sections often list codes
only (e.g. "外資賣超集中：0050(-48799)、2408(-14204)").

Rules (best-effort):
- If the code already appears as "名稱(代號)" or has a name right after it, we
  avoid double-inserting.
- We only map known codes; unknown codes are left as-is.

Usage:
  tw_md_add_names.py --in input.md --out output.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Keep in sync with bin/tw_make_table.py
NAME_MAP = {
    "0050": "元大台灣50",
    "00631L": "元大台灣50正2",
    "2330": "台積電",
    "2454": "聯發科",
    "2317": "鴻海",
    "2308": "台達電",
    "2344": "華邦電",
    "2327": "國巨",
    "2449": "京元電子",
    "2357": "華碩",
    "3017": "奇鋐",
    "2408": "南亞科",
    "2337": "旺宏",
    "8299": "群聯",
    "6669": "緯穎",
    "3491": "昇達科",
    "6285": "啟碁",
    "5388": "中磊",
    "8086": "宏捷科",
    "3105": "穩懋",
    "4979": "華星光",
    "3163": "波若威",
    "3363": "上詮",
    "3234": "光環",
    "3081": "聯亞",
    "6442": "光聖",
    "3450": "聯鈞",
}

# Match a standalone numeric code (4–6 digits) not adjacent to other digits.
CODE_RE = re.compile(r"(?<!\d)(\d{4,6})(?!\d)")

# If a code is immediately followed by a space + CJK, we assume name is already present.
HAS_NAME_AFTER_RE = re.compile(r"^(?:\s*[\u4e00-\u9fff])")

# Patterns like "2357（" are common in narrative lists.
# Be careful: "0050(-48799)" uses '(' to start a numeric value; don't treat that as code-parenthesis.
CODE_PAREN_FULL_RE = re.compile(r"(?<!\d)(\d{4,6})（")
CODE_PAREN_ASCII_RE = re.compile(r"(?<!\d)(\d{4,6})\((?![+\-\d])")


def add_names(text: str) -> str:
    """Insert names for bare stock codes in non-table lines."""

    def replace_code_paren(line: str) -> str:
        # Convert "<code>（" → "<name>(<code>)" (and drop the original fullwidth paren)
        def repl(m: re.Match) -> str:
            code = m.group(1)
            name = NAME_MAP.get(code)
            if not name:
                return m.group(0)
            return f"{name}({code})"

        line = CODE_PAREN_FULL_RE.sub(repl, line)
        line = CODE_PAREN_ASCII_RE.sub(repl, line)
        return line

    def repl_factory(line: str):
        def repl(m: re.Match) -> str:
            code = m.group(1)
            name = NAME_MAP.get(code)
            if not name:
                return code

            # Look ahead a few chars (within this line) to see if a name already exists.
            rest = line[m.end() : m.end() + 8]
            if HAS_NAME_AFTER_RE.match(rest):
                return code

            # If it's already in "名稱(代號)" form, code is preceded by '(' or '（'.
            prev = line[m.start() - 1 : m.start()] if m.start() > 0 else ""
            if prev in {"(", "（"}:
                return code

            # If code is preceded by a CJK name + whitespace (e.g. "緯穎 6669"),
            # prefer converting to "緯穎(6669)".
            before = line[max(0, m.start() - 6) : m.start()]
            if re.search(r"[\u4e00-\u9fff]\s*$", before):
                return f"({code})"

            return f"{code} {name}"

        return repl

    out_lines = []
    for line in text.splitlines(True):
        # Avoid touching markdown tables (header/separator/rows)
        if line.lstrip().startswith("|"):
            out_lines.append(line)
            continue

        line2 = replace_code_paren(line)
        out_lines.append(CODE_RE.sub(repl_factory(line2), line2))

    return "".join(out_lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    args = ap.parse_args()

    inp = Path(args.in_path).read_text(encoding="utf-8")
    out = add_names(inp)
    Path(args.out_path).write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
