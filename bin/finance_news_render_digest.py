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

    tw = pick(tw_items, args.max_tw)
    gl = pick(gl_items, args.max_global)

    now = datetime.now(ZoneInfo(args.tz)).strftime("%Y/%m/%d %H:%M")

    print(f"【財經新聞快報｜台灣＋國際】{now}（回顧近 5 小時｜RSS 去重）\n")

    print("## 台灣（最多 8 則）")
    for i, it in enumerate(tw, 1):
        title = (it.get("title") or it.get("headline") or "").strip()
        summ = one_line(it.get("raw_summary") or it.get("summary") or "")
        nums = extract_numbers(title + " " + summ)
        numtxt = ("；關鍵數字：" + ", ".join(nums)) if nums else ""
        print(f"{i}) **{title}**")
        print(f"- 重點：{summ if summ else '（摘要缺）'}{numtxt}")
        print(f"- 原文：[link]({it.get('link')})｜來源：{it.get('source')}\n")

    print("## 國際（最多 8 則）")
    for i, it in enumerate(gl, 1):
        title = (it.get("title") or it.get("headline") or "").strip()
        summ = one_line(it.get("raw_summary") or it.get("summary") or "")
        nums = extract_numbers(title + " " + summ)
        numtxt = ("；關鍵數字：" + ", ".join(nums)) if nums else ""
        print(f"{i}) **{title}**")
        print(f"- 重點：{summ if summ else '（摘要缺）'}{numtxt}")
        print(f"- 原文：[link]({it.get('link')})｜來源：{it.get('source')}\n")

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
