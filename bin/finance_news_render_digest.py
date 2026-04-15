#!/usr/bin/env python3
"""Render finance news digest markdown from finance_news_collect.py output.

Input JSON schema (current):
{
  "generated_at": "...",
  "window_hours": 5,
  "cutoff_utc": "...",
  "regions": {
    "taiwan": {"items": [...], "errors": [...]},
    "global": {"items": [...], "errors": [...]}
  }
}

We intentionally do *no* network calls here.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo


def pick(items, n=8):
    def key(it):
        p = it.get("published_at") or ""
        w = it.get("weight") or 0
        return (p, w)

    return sorted(items, key=key, reverse=True)[:n]


def _title_tokens(title: str) -> set[str]:
    """Tokenize title for clustering similar stories.

    - ascii words length>=3
    - ignore very common news words
    """
    t = (title or "").lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    words = [w for w in t.split() if len(w) >= 3]
    stop = {
        "live", "update", "updates", "today", "stock", "stocks", "market", "markets",
        "news", "says", "say", "said", "report", "reports", "amid", "after", "over",
        "with", "from", "into", "this", "that", "will", "would", "could",
        "company", "companies", "group", "shares", "share",
    }
    return {w for w in words if w not in stop and not w.isdigit()}


def _set_sim(a: set[str], b: set[str]) -> float:
    # If we can't extract tokens (e.g., pure CJK titles), do not merge here.
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


KEY_PAIRS = [
    {"amazon", "globalstar"},
    {"microsoft", "openai"},
    {"apple", "iphone"},
    {"tesla", "musk"},
]


def merge_similar_items(items: list[dict], threshold: float = 0.55) -> list[dict]:
    """Merge near-duplicate stories (same event, different outlets).

    This is a second-stage safety net beyond exact-url/title-sim dedup.

    Strategy:
    - greedy clustering over sorted items (newer/higher weight first)
    - if title token Jaccard >= threshold: merge links/sources into representative
    """
    out: list[dict] = []

    def sort_key(it):
        return (it.get("published_at") or "", it.get("weight") or 0)

    for it in sorted(items, key=sort_key, reverse=True):
        title = (it.get("title") or it.get("headline") or "").strip()
        toks = _title_tokens(title)

        merged = False
        for rep in out:
            rep_title = (rep.get("title") or rep.get("headline") or "").strip()
            rep_toks = rep.setdefault("_title_tokens", _title_tokens(rep_title))
            sim = _set_sim(toks, rep_toks)
            inter = toks & rep_toks

            strong_entity_match = any(pair.issubset(inter) for pair in KEY_PAIRS)

            # Merge when we have enough shared "entity" tokens.
            # - Either overall token overlap is decent, OR we detect a strong entity pair match.
            if len(inter) >= 2 and (sim >= threshold or strong_entity_match):
                # merge links
                rep.setdefault("alt_links", [])
                link = it.get("link")
                if link and link != rep.get("link") and link not in rep["alt_links"]:
                    rep["alt_links"].append(link)

                # merge sources
                rep.setdefault("alt_sources", [])
                src = it.get("source")
                if src and src != rep.get("source") and src not in rep["alt_sources"]:
                    rep["alt_sources"].append(src)

                merged = True
                break

        if not merged:
            out.append(dict(it))

    # strip helper field
    for it in out:
        if "_title_tokens" in it:
            del it["_title_tokens"]

    return out


def extract_numbers(text: str):
    if not text:
        return []
    nums = re.findall(
        r"[-+]?\d+(?:\.\d+)?%|[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?",
        text,
    )
    out = []
    for x in nums:
        if x not in out:
            out.append(x)
    return out[:4]


def one_line(s: str, limit: int = 90) -> str:
    s = (s or "").replace("\u3000", " ").strip().split("\n")[0].strip()
    if len(s) > limit:
        s = s[:limit] + "…"
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--tz", default="Asia/Taipei")
    ap.add_argument("--max-tw", type=int, default=8)
    ap.add_argument("--max-global", type=int, default=8)
    args = ap.parse_args()

    j = json.load(open(args.input, "r", encoding="utf-8"))
    regions = j.get("regions") or {}
    tw_items = (regions.get("taiwan") or {}).get("items") or []
    gl_items = (regions.get("global") or {}).get("items") or []

    # Second-stage merge to avoid "same event, many outlets" spam.
    tw_items = merge_similar_items(tw_items)
    gl_items = merge_similar_items(gl_items)

    tw = pick(tw_items, args.max_tw)
    gl = pick(gl_items, args.max_global)

    now = datetime.now(ZoneInfo(args.tz)).strftime("%Y/%m/%d %H:%M")

    print(f"【財經新聞快報｜台灣＋國際】{now}（回顧近 5 小時｜RSS 去重）\n")

    def render_item(i: int, it: dict) -> None:
        title = (it.get("title") or it.get("headline") or "").strip()
        summ = one_line(it.get("raw_summary") or it.get("summary") or "")
        nums = extract_numbers(title + " " + summ)
        numtxt = ("；關鍵數字：" + ", ".join(nums)) if nums else ""

        print(f"{i}) **{title}**")
        print(f"- 重點：{summ if summ else '（摘要缺）'}{numtxt}")
        print(f"- 原文：[link]({it.get('link')})｜來源：{it.get('source')}")

        extras = []
        if it.get("alt_sources"):
            extras.append("其他來源：" + " / ".join(it.get("alt_sources") or []))
        if it.get("alt_links"):
            extras.append("延伸閱讀：" + " ".join([f"[link]({u})" for u in (it.get("alt_links") or [])[:5]]))
        if extras:
            print("- " + "｜".join(extras))

        print("")

    print("## 台灣（最多 8 則）")
    for i, it in enumerate(tw, 1):
        render_item(i, it)

    print("## 國際（最多 8 則）")
    for i, it in enumerate(gl, 1):
        render_item(i, it)

    print("---")
    print("### 今日主軸（3 點）")
    print("- AI/科技股估值與資本支出（CAPEX）敘事持續牽動風險偏好。")
    print("- 油價/地緣風險與利率路徑預期，仍是宏觀擾動來源。")
    print("- 低軌衛星＋光通訊/雷射（矽光子/CPO）相關新聞若出現，優先追蹤。")

    print("\n### 需要追蹤的事件（3 點）")
    print("- 重大財報/法說：指引是否下修或資本支出是否轉向。")
    print("- 美債殖利率/美元：是否出現方向性波動（影響成長股估值）。")
    print("- 產業題材：低軌衛星與光通訊鏈的訂單/投資/供應瓶頸訊號。")

    errs = []
    errs.extend((regions.get("taiwan") or {}).get("errors") or [])
    errs.extend((regions.get("global") or {}).get("errors") or [])
    if errs:
        print("\n### 資料來源狀態")
        for e in errs[:10]:
            print(f"- {e.get('source')}: {e.get('error')}")


if __name__ == "__main__":
    main()
