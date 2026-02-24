#!/usr/bin/env python3
"""Generate a research-oriented US close summary (zh-TW) from cached market data.

Inputs:
- tmp/us-data.json: produced by bin/us_report_data.py
- tmp/us-table.md: produced by bin/us_make_table.py

Output:
- tmp/us-summary.md: markdown body (starts with '# 美股收盤研究摘要（快取）')

Design goal:
- Always produce non-empty, information-dense commentary even when no news feeds are available.
- Use only the cached price/volume and indicator data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _fmt_num(x, digits=2):
    if x is None:
        return "NA"
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "NA"


def _fmt_int(x):
    if x is None:
        return "NA"
    try:
        return f"{int(float(x)):,}"
    except Exception:
        return "NA"


def _fmt_pct(x, digits=2):
    if x is None:
        return "NA"
    try:
        return f"{float(x):+.{digits}f}%"
    except Exception:
        return "NA"


def pick_movers(rows: List[Dict[str, Any]], n_up=3, n_dn=2) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    valid = [r for r in rows if isinstance(r.get("chg_pct"), (int, float))]
    ups = sorted(valid, key=lambda r: r["chg_pct"], reverse=True)[:n_up]
    dns = sorted(valid, key=lambda r: r["chg_pct"])[:n_dn]
    return ups, dns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (trading day)", required=True)
    ap.add_argument("--data", default="tmp/us-data.json")
    ap.add_argument("--out", default="tmp/us-summary.md")
    args = ap.parse_args()

    d = json.loads(Path(args.data).read_text(encoding="utf-8"))
    # Schema: tickers is a dict: {"QQQ": {close, chg, chg_pct, volume, date, ok}, ...}
    #         indicators is a dict: {"VIX": {...}, "XAUUSD": {...}, ...}
    tickers_dict: Dict[str, Dict[str, Any]] = d.get("tickers", {})
    indicators_dict: Dict[str, Dict[str, Any]] = d.get("indicators", {})

    # Normalize to rows with ticker field for sorting
    tickers: List[Dict[str, Any]] = [dict({"ticker": k}, **(v or {})) for k, v in tickers_dict.items()]
    indicators: List[Dict[str, Any]] = [dict({"symbol": k}, **(v or {})) for k, v in indicators_dict.items()]

    by = {r.get("ticker"): r for r in tickers}
    ind = {r.get("symbol"): r for r in indicators}

    qqq = by.get("QQQ", {})

    ups, dns = pick_movers(tickers)

    def line_for(r: Dict[str, Any]) -> str:
        t = r.get("ticker", "?")
        return f"{t} {_fmt_pct(r.get('chg_pct'), 2)}"

    # Build summary
    lines: List[str] = []
    lines.append("# 美股收盤研究摘要（快取）\n")
    lines.append("## A) 追蹤清單快覽")
    lines.append("- 下方表格已包含：**收盤價 / 漲跌 / 成交量**。")
    if qqq:
        lines.append(
            f"- 大盤代理（QQQ）：收 **{_fmt_num(qqq.get('close'), 2)}**，{_fmt_num(qqq.get('chg'), 2)}（{_fmt_pct(qqq.get('chg_pct'), 2)}），量 **{_fmt_int(qqq.get('volume'))}**。"
        )

    lines.append("\n## B) 族群/主題輪動重點（3–5 點）")
    if ups:
        lines.append(
            "- 追蹤清單內的領漲集中在："
            + "、".join([line_for(r) for r in ups])
            + "；短線屬於『風險偏好回升』的典型表現，但也要留意隔日是否量縮回吐。"
        )
    if dns:
        lines.append(
            "- 相對偏弱/拖累者："
            + "、".join([line_for(r) for r in dns])
            + "；若屬於同一主題（例如記憶體/網通/雲端），可能意味市場在做族群內輪動而非全面轉弱。"
        )

    # Semis / AI chain focus
    amd = by.get("AMD", {})
    nvda = by.get("NVDA", {})
    mu = by.get("MU", {})
    avgo = by.get("AVGO", {})
    if amd or nvda or mu or avgo:
        lines.append(
            "- 半導體/AI 鏈條："
            f"AMD {_fmt_pct(amd.get('chg_pct'), 2)}、NVDA {_fmt_pct(nvda.get('chg_pct'), 2)}、MU {_fmt_pct(mu.get('chg_pct'), 2)}、AVGO {_fmt_pct(avgo.get('chg_pct'), 2)}。"
            "可用『AI 投資 vs 獲利兌現』分歧理解：同族群可能出現強弱分化（追價與獲利了結並存）。"
        )

    # Mega-cap breadth
    aapl = by.get("AAPL", {})
    goog = by.get("GOOG", {})
    tsla = by.get("TSLA", {})
    if aapl or goog or tsla:
        lines.append(
            "- mega-cap 方向："
            f"AAPL {_fmt_pct(aapl.get('chg_pct'), 2)}、GOOG {_fmt_pct(goog.get('chg_pct'), 2)}、TSLA {_fmt_pct(tsla.get('chg_pct'), 2)}。"
            "若指數上漲同時大型股多數同向，代表上攻『廣度』較佳；若只靠少數權值，隔日震盪機率較高。"
        )

    lines.append("\n## C) 重要事件 / 新聞（4–7 點，附連結）")
    lines.append(
        "- （目前流程未整合自動新聞抓取）先提供 3 個『快速對照』入口；如果你希望我每天固定抓新聞，我會把 RSS 收集整合進這個 cron。"
    )
    lines.append("  - Investing.com（US stocks）：<https://www.investing.com/news/stock-market-news>")
    lines.append("  - MarketWatch：<https://www.marketwatch.com/>")
    lines.append("  - Reuters Markets（可能需權限）：<https://www.reuters.com/markets/us/>")

    lines.append("\n## D) 額外市場指標：VIX、金、銀、BTC（引用表格數字並解讀）")
    vix = ind.get("VIX", {})
    xau = ind.get("XAUUSD", {})
    xag = ind.get("XAGUSD", {})
    btc = ind.get("BTCUSD", {})
    if vix:
        lines.append(
            f"- VIX：收 **{_fmt_num(vix.get('close'), 2)}**，{_fmt_num(vix.get('chg'), 2)}（{_fmt_pct(vix.get('chg_pct'), 2)}）。"
            "VIX 上升通常代表避險需求增加；若同時指數上漲，常見於『反彈但不放心』的盤。"
        )
    if xau or xag:
        lines.append(
            f"- 貴金屬：金(XAUUSD) {_fmt_pct(xau.get('chg_pct'), 2)}、銀(XAGUSD) {_fmt_pct(xag.get('chg_pct'), 2)}。"
            "若股市走強、金銀走弱，偏向風險資產勝出；反之則需留意資金轉向防禦。"
        )
    if btc:
        lines.append(
            f"- BTC：收 **{_fmt_num(btc.get('close'), 2)}**，{_fmt_num(btc.get('chg'), 2)}（{_fmt_pct(btc.get('chg_pct'), 2)}）。"
            "若與 QQQ 同向放大通常代表風險偏好一致；若背離，常見於流動性/槓桿資金調整。"
        )

    lines.append("\n## E) 潛在轉強名單（追蹤清單以外 3–5 檔；含關鍵價位/風險一句）")
    lines.append(
        "- 這版快取沒有自動掃描全市場，因此先給『方法』：從你常看的主線（AI/半導體/雲端）挑 3–5 檔，隔日用『站回 20 日線 + 量能放大 + 相對強弱』做二次篩選。"
    )
    lines.append("  - 若你希望我自動產出名單：我可以新增一個『候選清單』設定檔（例如 SPY/SMH/IGV + 20–50 檔）每日用 Stooq 拉數據做 RS/均線打分。")

    out = Path(args.out)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
