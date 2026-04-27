#!/usr/bin/env python3
"""Similarity gate for self-plagiarism / template drift.

Design goals:
- No heavy dependencies (stdlib only).
- Fast enough to run in cron.
- Produces a human-readable report (markdown) + machine report (json).
- Supports per-section corpus comparison (e.g., US report compares only reports/us).

Scoring (0..1, higher means more similar):
- lexical_score: simhash token similarity
- structural_score: outline/section-label similarity
- thesis_score: hashed-embedding cosine similarity over extracted thesis
- overall_score: weighted sum

Note: "embedding" here is a lightweight hashed vector embedding (feature hashing),
so it works offline without API keys. If you later want semantic embeddings, this
script can be extended to call an embedding API.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Iterable


# --------------------------- text utils ---------------------------

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def strip_code_blocks(md: str) -> str:
    # Remove fenced code blocks to reduce template noise.
    return re.sub(r"```.*?```", "\n", md, flags=re.S)


def normalize_ws(s: str) -> str:
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def tokenize(s: str) -> list[str]:
    """Tokenize for simhash.

    Works for mixed zh/en:
    - keep ascii words/numbers
    - keep CJK chars as individual tokens
    """
    s = s.lower()
    out: list[str] = []
    out.extend(re.findall(r"[a-z0-9]{2,}", s))
    out.extend(re.findall(r"[\u4e00-\u9fff]", s))
    return out


# --------------------------- simhash ---------------------------

def _fnv1a_64(s: str) -> int:
    # Deterministic 64-bit hash.
    h = 1469598103934665603
    for b in s.encode("utf-8", errors="ignore"):
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def simhash64(tokens: Iterable[str]) -> int:
    """Compute a 64-bit simhash."""
    # simple weighting: token frequency
    freq: dict[str, int] = {}
    for t in tokens:
        if not t:
            continue
        freq[t] = freq.get(t, 0) + 1

    vec = [0] * 64
    for t, w in freq.items():
        hv = _fnv1a_64(t)
        for i in range(64):
            bit = (hv >> i) & 1
            vec[i] += w if bit else -w

    out = 0
    for i, v in enumerate(vec):
        if v > 0:
            out |= (1 << i)
    return out


def hamming64(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def simhash_similarity(a: int, b: int) -> float:
    # 1.0 identical, 0.0 maximally different
    return 1.0 - (hamming64(a, b) / 64.0)


# --------------------------- structural features ---------------------------

STRUCT_LABELS = [
    ("five", re.compile(r"五行總結|5\s*行總結|five[- ]line", re.I)),
    ("highlights", re.compile(r"今日重點|重點|highlights", re.I)),
    ("numbers", re.compile(r"重要數字|關鍵數字|numbers", re.I)),
    ("actions", re.compile(r"行動建議|待查|next steps|actions", re.I)),
    ("quote", re.compile(r"金句|quote", re.I)),
    ("sector", re.compile(r"族群|輪動|rotation|sector", re.I)),
    ("news", re.compile(r"重要事件|新聞|news", re.I)),
]


def extract_outline(md: str) -> list[str]:
    lines = md.splitlines()
    outline: list[str] = []

    for ln in lines:
        m = re.match(r"^(#{1,4})\s+(.+)$", ln.strip())
        if not m:
            continue
        level = len(m.group(1))
        title = normalize_ws(m.group(2))
        if not title:
            continue

        # Map some known headers to stable labels to detect structure reuse.
        label = None
        for name, rx in STRUCT_LABELS:
            if rx.search(title):
                label = name
                break
        if label is None:
            # general header bucket by level
            label = f"h{level}"

        outline.append(label)

    # Also add coarse stats about list usage
    bullets = sum(1 for ln in lines if ln.strip().startswith("- "))
    ordered = sum(1 for ln in lines if re.match(r"^\s*\d+\.\s+", ln))
    if bullets:
        outline.append("bullets")
    if ordered:
        outline.append("ordered")

    return outline


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# --------------------------- thesis extraction + embedding ---------------------------

def _extract_date_yyyymmdd(text: str) -> str:
    """Extract YYYY-MM-DD from text (supports YYYY/MM/DD or YYYY-MM-DD)."""
    m = re.search(r"(20\d{2})[/-](\d{2})[/-](\d{2})", text)
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def extract_thesis(md: str) -> str:
    """Heuristic thesis extraction (offline).

    Priority:
    1) First bullet under 五行總結
    2) First non-empty paragraph after the H1
    3) Fallback: first non-empty line
    """
    lines = [ln.rstrip() for ln in md.splitlines()]

    # Find 五行總結 section start
    for i, ln in enumerate(lines):
        if re.search(r"五行總結|5\s*行總結|five[- ]line", ln, re.I):
            # scan next 25 lines for first bullet/line of content
            for j in range(i + 1, min(i + 26, len(lines))):
                x = lines[j].strip()
                if not x:
                    continue
                x = re.sub(r"^[-*]\s+", "", x)
                x = re.sub(r"^\d+\.\s+", "", x)
                x = normalize_ws(x)
                if len(x) >= 12:
                    return x[:80]
            break

    # After H1
    h1_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            h1_idx = i
            break
    if h1_idx is not None:
        for j in range(h1_idx + 1, min(h1_idx + 80, len(lines))):
            x = lines[j].strip()
            if not x or x.startswith("#") or x.startswith("-"):
                continue
            # Skip markdown tables (common fixed headers) which create false positives.
            if x.startswith("|"):
                continue
            x = normalize_ws(x)
            if len(x) >= 12:
                return x[:160]

    # Fallback: first meaningful non-empty line (skip headings + table rows)
    for ln in lines:
        x = normalize_ws(ln)
        if not x:
            continue
        if x.startswith("#") or x.startswith("|"):
            continue
        return x[:160]

    return ""


def hashed_embedding(text: str, dim: int = 256, ngram: int = 3) -> list[float]:
    """Cheap embedding: hashed character n-gram vector.

    Produces a dense float vector length=dim.
    """
    v = [0.0] * dim
    t = normalize_ws(text)
    if not t:
        return v

    # char n-grams
    chars = list(t)
    if len(chars) < ngram:
        grams = [t]
    else:
        grams = ["".join(chars[i : i + ngram]) for i in range(0, len(chars) - ngram + 1)]

    for g in grams:
        h = _fnv1a_64(g)
        idx = h % dim
        sign = 1.0 if ((h >> 8) & 1) else -1.0
        v[idx] += sign

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in v))
    if norm > 0:
        v = [x / norm for x in v]
    return v


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


# --------------------------- core ---------------------------

@dataclasses.dataclass
class Score:
    path: str
    lexical: float
    structural: float
    thesis: float
    overall: float
    thesis_text: str


def score_pair(
    draft_md: str,
    other_md: str,
    weights: tuple[float, float, float],
    *,
    section: str = "",
) -> tuple[float, float, float, float, str]:
    w_lex, w_struct, w_thesis = weights

    draft_clean = strip_code_blocks(draft_md)
    other_clean = strip_code_blocks(other_md)

    # Lexical
    dh = simhash64(tokenize(draft_clean))
    oh = simhash64(tokenize(other_clean))
    lexical = simhash_similarity(dh, oh)

    # Structural
    structural = jaccard(extract_outline(draft_clean), extract_outline(other_clean))

    # Thesis
    draft_thesis = extract_thesis(draft_clean)
    other_thesis = extract_thesis(other_clean)

    # Option (2) continuation for finance_news: avoid "template headline" dominating similarity.
    # If thesis is just the fixed "【財經新聞快報｜...】YYYY/MM/DD HH:MM（回顧...）" pattern,
    # it is expected to be near-identical day-to-day. Treat thesis similarity as 0 and let lexical/structure govern.
    if section.strip().lower() == "finance_news":
        if draft_thesis.startswith("【財經新聞快報") and other_thesis.startswith("【財經新聞快報"):
            thesis = 0.0
        else:
            thesis = cosine(hashed_embedding(draft_thesis), hashed_embedding(other_thesis)) if (draft_thesis and other_thesis) else 0.0
    else:
        thesis = cosine(hashed_embedding(draft_thesis), hashed_embedding(other_thesis)) if (draft_thesis and other_thesis) else 0.0

    overall = (w_lex * lexical) + (w_struct * structural) + (w_thesis * thesis)
    return lexical, structural, thesis, overall, other_thesis


def find_corpus(section: str, repo_root: Path) -> Path:
    # Map section to reports folder
    section = section.strip().lower()
    mapping = {
        "tw": repo_root / "reports" / "tw",
        "us": repo_root / "reports" / "us",
        "youtube": repo_root / "reports" / "youtube",
        "guai": repo_root / "reports" / "guai",
        "finance_news": repo_root / "reports" / "finance_news",
        "moltbook": repo_root / "reports" / "moltbook",
        "analysis": repo_root / "reports" / "analysis",
    }
    p = mapping.get(section)
    if p is None:
        raise SystemExit(f"Unknown section: {section}. Expected one of: {', '.join(sorted(mapping.keys()))}")
    return p


def list_md_files(dir_path: Path) -> list[Path]:
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() == ".md"] )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True, help="Path to draft markdown")
    ap.add_argument("--section", required=True, help="Corpus section: us|tw|youtube|...")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--top", type=int, default=5, help="Top N similar docs to report")
    ap.add_argument("--block", type=float, default=0.86, help="Overall similarity >= block => exit 1")
    ap.add_argument("--warn", type=float, default=0.78, help="Overall similarity >= warn => exit 0 but warn")
    ap.add_argument("--weights", default="0.45,0.05,0.50", help="lex,struct,thesis weights")
    ap.add_argument("--out-json", default="tmp/similarity_report.json")
    ap.add_argument("--out-md", default="tmp/similarity_report.md")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    draft_path = Path(args.draft).resolve()
    if not draft_path.exists():
        raise SystemExit(f"draft not found: {draft_path}")

    corpus_dir = find_corpus(args.section, repo_root)
    files = list_md_files(corpus_dir)

    draft_md = read_text(draft_path)

    # Parse weights
    try:
        parts = [float(x.strip()) for x in args.weights.split(",")]
        if len(parts) != 3:
            raise ValueError
        s = sum(parts)
        weights = (parts[0] / s, parts[1] / s, parts[2] / s) if s else (0.3, 0.3, 0.4)
    except Exception:
        weights = (0.3, 0.3, 0.4)

    draft_thesis = extract_thesis(strip_code_blocks(draft_md))
    draft_date = _extract_date_yyyymmdd(draft_thesis)

    scored: list[Score] = []
    for p in files:
        # skip self if draft is already in corpus path
        if p.resolve() == draft_path:
            continue
        other_md = read_text(p)

        # Option (2): allow multiple intraday finance_news updates.
        # If the other doc looks like the same calendar date, ignore it in corpus comparison.
        if args.section.strip().lower() == "finance_news" and draft_date:
            other_thesis = extract_thesis(strip_code_blocks(other_md))
            other_date = _extract_date_yyyymmdd(other_thesis)
            if other_date and other_date == draft_date:
                continue

        lex, struct, th, overall, other_thesis = score_pair(draft_md, other_md, weights, section=args.section)
        scored.append(Score(path=str(p), lexical=lex, structural=struct, thesis=th, overall=overall, thesis_text=other_thesis))

    scored.sort(key=lambda x: x.overall, reverse=True)
    top = scored[: max(0, int(args.top))]

    verdict = "PASS"
    exit_code = 0
    if top and top[0].overall >= args.block:
        verdict = "BLOCK"
        exit_code = 1
    elif top and top[0].overall >= args.warn:
        verdict = "WARN"
        exit_code = 0

    report = {
        "verdict": verdict,
        "section": args.section,
        "draft": str(draft_path),
        "draft_thesis": draft_thesis,
        "thresholds": {"warn": args.warn, "block": args.block},
        "weights": {"lexical": weights[0], "structural": weights[1], "thesis": weights[2]},
        "top": [dataclasses.asdict(x) for x in top],
    }

    # write outputs
    out_json = (repo_root / args.out_json).resolve() if not os.path.isabs(args.out_json) else Path(args.out_json)
    out_md = (repo_root / args.out_md).resolve() if not os.path.isabs(args.out_md) else Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = []
    md_lines.append(f"# Similarity gate report")
    md_lines.append("")
    md_lines.append(f"- verdict: **{verdict}**")
    md_lines.append(f"- section: `{args.section}`")
    md_lines.append(f"- draft: `{draft_path}`")
    md_lines.append(f"- draft_thesis: {draft_thesis if draft_thesis else '（無）'}")
    md_lines.append(f"- thresholds: warn>={args.warn:.2f}, block>={args.block:.2f}")
    md_lines.append(f"- weights: lexical={weights[0]:.2f}, structural={weights[1]:.2f}, thesis={weights[2]:.2f}")
    md_lines.append("")

    if not top:
        md_lines.append("（corpus 空或沒有可比對檔案）")
    else:
        md_lines.append("## Top similar")
        for i, x in enumerate(top, 1):
            md_lines.append(f"### {i}. `{x.path}`")
            md_lines.append(f"- overall: **{x.overall:.3f}**")
            md_lines.append(f"- lexical: {x.lexical:.3f}")
            md_lines.append(f"- structural: {x.structural:.3f}")
            md_lines.append(f"- thesis: {x.thesis:.3f}")
            if x.thesis_text:
                md_lines.append(f"- other_thesis: {x.thesis_text}")
            md_lines.append("")

    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # Print a one-line summary for cron logs
    best = top[0].overall if top else 0.0
    print(f"SIM_GATE {verdict} best_overall={best:.3f} report={out_md}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
