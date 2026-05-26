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
from difflib import SequenceMatcher
from datetime import datetime
from zoneinfo import ZoneInfo


AI_KEYWORDS = [
    "ai", "artificial intelligence", "generative ai", "genai", "agentic", "ai agent",
    "openai", "anthropic", "chatgpt", "gemini", "copilot", "llm", "gpu", "tpu",
    "accelerator", "data center", "datacenter", "server", "semiconductor", "chip",
    "hbm", "asic", "cpo", "silicon photonics", "optical", "inference", "training",
    "人工智慧", "生成式ai", "生成式 ai", "ai代理", "ai 代理", "算力", "資料中心",
    "數據中心", "伺服器", "半導體", "晶片", "先進封裝", "矽光子", "光通訊",
    "推論", "訓練", "機器人", "輝達", "黃仁勳",
]

TAIWAN_MARKET_KEYWORDS = [
    "台股", "台灣股市", "加權指數", "櫃買", "上市", "上櫃", "權值股",
    "股票", "股市", "股價", "股東會", "買超", "賣超", "外資", "三大法人",
    "etf", "基金", "投信", "券商", "金管會", "銀行", "金控", "保險", "壽險",
    "匯率", "新台幣", "美元", "利率", "升息", "降息", "央行", "聯準會",
    "通膨", "cpi", "殖利率", "美債", "債券", "期貨", "原油", "油價",
    "能源", "電力", "電價", "經濟", "景氣", "產業", "營收", "獲利",
    "財報", "法說", "併購", "投資", "市場", "供應鏈", "半導體", "電子股",
    "金融股", "航運股", "觀光股", "傳產", "證券", "有價證券", "資金", "華爾街",
    "企業", "商會", "台積電", "聯發科", "鴻海", "台達電",
    "markets", "market", "stocks", "stock", "equities", "inflation", "rate",
    "yield", "oil", "energy", "earnings", "revenue", "economy", "investment",
]

TAIWAN_OFF_TOPIC_KEYWORDS = [
    "頭獎", "今彩", "大樂透", "威力彩", "彩券", "mlb", "nba", "中職",
    "棒球", "籃球", "機油", "引擎", "熱浪", "氣溫", "公共衛生",
]

STOCK_ALIASES = {
    "NVDA": ["NVDA", "Nvidia", "NVIDIA", "輝達", "英偉達"],
    "AMD": ["AMD", "超微"],
    "AVGO": ["AVGO", "Broadcom", "博通"],
    "TSM": ["TSM", "TSMC", "Taiwan Semiconductor", "台積電", "台積"],
    "ASML": ["ASML", "艾司摩爾"],
    "MU": ["MU", "Micron", "美光"],
    "MRVL": ["MRVL", "Marvell", "邁威爾"],
    "ARM": ["ARM", "Arm Holdings"],
    "ANET": ["ANET", "Arista"],
    "SMCI": ["SMCI", "Super Micro", "Supermicro", "美超微"],
    "MSFT": ["MSFT", "Microsoft", "微軟"],
    "GOOGL": ["GOOGL", "GOOG", "Alphabet", "Google", "谷歌"],
    "AMZN": ["AMZN", "Amazon", "AWS", "亞馬遜"],
    "META": ["META", "Meta", "臉書"],
    "ORCL": ["ORCL", "Oracle", "甲骨文"],
    "PLTR": ["PLTR", "Palantir"],
    "AAPL": ["AAPL", "Apple", "蘋果"],
    "TSLA": ["TSLA", "Tesla", "特斯拉"],
    "2330": ["2330", "台積電", "台積"],
    "2454": ["2454", "聯發科"],
    "2382": ["2382", "廣達"],
    "3231": ["3231", "緯創"],
    "6669": ["6669", "緯穎"],
    "2356": ["2356", "英業達"],
    "2317": ["2317", "鴻海", "富士康"],
    "3017": ["3017", "奇鋐"],
    "3324": ["3324", "雙鴻"],
    "3661": ["3661", "世芯"],
    "3443": ["3443", "創意"],
    "3035": ["3035", "智原"],
    "5274": ["5274", "信驊"],
    "2449": ["2449", "京元電子"],
    "3711": ["3711", "日月光投控"],
    "2308": ["2308", "台達電"],
    "2345": ["2345", "智邦"],
    "6213": ["6213", "聯茂"],
    "2383": ["2383", "台光電"],
    "8299": ["8299", "群聯"],
    "2376": ["2376", "技嘉"],
    "2357": ["2357", "華碩"],
    "2327": ["2327", "國巨"],
    "2492": ["2492", "華新科"],
}

STOCK_DISPLAY = {
    "NVDA": "輝達(NVDA)",
    "AMD": "超微(AMD)",
    "AVGO": "博通(AVGO)",
    "TSM": "台積電(TSM)",
    "ASML": "ASML",
    "MU": "美光(MU)",
    "MRVL": "Marvell(MRVL)",
    "ARM": "Arm(ARM)",
    "ANET": "Arista(ANET)",
    "SMCI": "美超微(SMCI)",
    "MSFT": "微軟(MSFT)",
    "GOOGL": "Alphabet(GOOGL)",
    "AMZN": "Amazon(AMZN)",
    "META": "Meta(META)",
    "ORCL": "Oracle(ORCL)",
    "PLTR": "Palantir(PLTR)",
    "AAPL": "Apple(AAPL)",
    "TSLA": "Tesla(TSLA)",
    "2330": "台積電(2330)",
    "2454": "聯發科(2454)",
    "2382": "廣達(2382)",
    "3231": "緯創(3231)",
    "6669": "緯穎(6669)",
    "2356": "英業達(2356)",
    "2317": "鴻海(2317)",
    "3017": "奇鋐(3017)",
    "3324": "雙鴻(3324)",
    "3661": "世芯(3661)",
    "3443": "創意(3443)",
    "3035": "智原(3035)",
    "5274": "信驊(5274)",
    "2449": "京元電子(2449)",
    "3711": "日月光投控(3711)",
    "2308": "台達電(2308)",
    "2345": "智邦(2345)",
    "6213": "聯茂(6213)",
    "2383": "台光電(2383)",
    "8299": "群聯(8299)",
    "2376": "技嘉(2376)",
    "2357": "華碩(2357)",
    "2327": "國巨(2327)",
    "2492": "華新科(2492)",
}

GLOBAL_TITLE_TRANSLATIONS = {
    "AMD, Broadcom and Google Intensify Anti-Nvidia Offensive as AI Semiconductor Landscape Faces Potential Realignment - economy.ac": "AMD、博通與 Google 加強反輝達攻勢，AI 半導體版圖可能重新洗牌",
    "Marvell on the Eve of Earnings: Wall Street Collectively Raises Price Targets, Can Nvidia and AMD’s Double Endorsement Deliver on the AI Narrative? - TradingKey": "Marvell 財報前夕華爾街同步調高目標價，輝達與 AMD 雙重背書能否支撐 AI 題材？",
    "Here's What I Think Is Going on With Nvidia Stock After the AI Giant's Showstopping Earnings Report - The Motley Fool": "AI 巨頭交出亮眼財報後，輝達股價接下來可能怎麼走",
    "NVIDIA Corporation stock (US67066G1040): record AI earnings keep attention high - AD HOC NEWS": "輝達創紀錄 AI 財報讓市場關注度維持高檔",
    "Infineon Showcases Semiconductor Solutions at PCIM Europe ’26 - Bisinfotech": "英飛凌於 PCIM Europe 2026 展示半導體解決方案",
    "The 3-Stock Custom Silicon Basket That Could Outperform Nvidia by 2030 - The Globe and Mail": "2030 年前可能跑贏輝達的 3 檔客製化晶片組合",
    "Singapore pressed to adopt AI-led checks after Nvidia case - Singapore Business Review": "輝達事件後，新加坡被要求採用 AI 主導審查",
    "The 'Next Nvidia' Trade? Why Investors Are Suddenly Watching Advanced Micro Devices, Arm Holdings, and Marvell Technology - Yahoo Finance": "「下一個輝達」交易？為何投資人突然關注超微、Arm 與 Marvell",
    "The 3-Stock Custom Silicon Basket That Could Outperform Nvidia by 2030 - The Motley Fool": "2030 年前可能跑贏輝達的 3 檔客製化晶片組合",
}


def _body_text(it: dict) -> str:
    text = " ".join(
        str(it.get(k) or "")
        for k in ("title", "headline", "raw_summary", "summary")
    )
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)
    return text


def extract_related_stocks(text: str) -> list[str]:
    out: list[str] = []
    haystack = text or ""
    haystack_lower = haystack.lower()
    for symbol, aliases in STOCK_ALIASES.items():
        for alias in aliases:
            if re.search(r"[A-Za-z0-9]", alias):
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", haystack, re.I):
                    out.append(symbol)
                    break
            elif alias.lower() in haystack_lower:
                out.append(symbol)
                break
    # Prefer Taiwan common stock code over ADR ticker when the same company is named in Chinese copy.
    if "2330" in out and "TSM" in out:
        out.remove("TSM")
    return [STOCK_DISPLAY.get(x, x) for x in out[:6]]


def display_title(it: dict, region: str) -> str:
    title = (it.get("title") or it.get("headline") or "").strip()
    if region != "global":
        return title
    return (it.get("title_zh") or GLOBAL_TITLE_TRANSLATIONS.get(title) or title).strip()


def ai_relevance(it: dict) -> int:
    text = _body_text(it).lower()
    score = 0
    for kw in AI_KEYWORDS:
        if kw.lower() in text:
            score += 3 if kw.lower() in {"ai", "人工智慧", "算力", "gpu", "hbm", "資料中心", "伺服器"} else 2
    score += min(len(extract_related_stocks(_body_text(it))), 4)
    if "aggregated" in (it.get("tags") or []):
        score += 1
    return score


def taiwan_market_relevance(it: dict) -> int:
    text = _body_text(it).lower()
    title = str(it.get("title") or it.get("headline") or "").lower()
    score = 0

    for kw in TAIWAN_MARKET_KEYWORDS:
        if kw.lower() in text:
            score += 2 if kw in {"台股", "台灣股市", "加權指數", "櫃買", "金管會", "匯率", "新台幣"} else 1

    stocks = extract_related_stocks(_body_text(it))
    score += min(len(stocks) * 2, 6)

    tags = set(it.get("tags") or [])
    if score > 0 and tags & {"finance", "stocks", "equities", "macro"}:
        score += 1

    if any(kw.lower() in title for kw in TAIWAN_OFF_TOPIC_KEYWORDS):
        score -= 8

    return score


def pick_ai_first(items, n=8):
    def key(it):
        p = it.get("published_at") or ""
        w = it.get("weight") or 0
        return (ai_relevance(it), p, w)

    ranked = sorted(items, key=key, reverse=True)
    ai_ranked = [it for it in ranked if ai_relevance(it) > 0]
    return (ai_ranked or ranked)[:n]


def pick_taiwan_non_ai(items, n=8):
    """Prefer Taiwan market news that is less directly tied to AI.

    The digest is still allowed to include AI-related Taiwan stories when the
    recent window does not have enough non-AI market news, but they should not
    dominate the Taiwan section.
    """

    def recency_key(it):
        return (it.get("published_at") or "", it.get("weight") or 0)

    market_items = [it for it in items if taiwan_market_relevance(it) > 0]
    ranked = sorted(market_items or items, key=recency_key, reverse=True)
    low_ai = [it for it in ranked if ai_relevance(it) == 0]
    weak_ai = [it for it in ranked if 0 < ai_relevance(it) <= 2]
    ai_related = sorted(
        [it for it in ranked if ai_relevance(it) > 2],
        key=lambda it: (ai_relevance(it), it.get("published_at") or "", it.get("weight") or 0),
    )

    picked = (low_ai + weak_ai + ai_related)[:n]
    return picked


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


def _title_text_sim(a: str, b: str) -> float:
    a2 = re.sub(r"\s+", "", (a or "").lower())
    b2 = re.sub(r"\s+", "", (b or "").lower())
    for boilerplate in ("【", "】", "(", ")", "（", "）", "公告", "本公司"):
        a2 = a2.replace(boilerplate, "")
        b2 = b2.replace(boilerplate, "")
    if not a2 or not b2:
        return 0.0
    return SequenceMatcher(None, a2, b2).ratio()


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
            text_sim = _title_text_sim(title, rep_title)
            inter = toks & rep_toks

            strong_entity_match = any(pair.issubset(inter) for pair in KEY_PAIRS)

            # Merge when we have enough shared "entity" tokens.
            # - Either overall token overlap is decent, OR we detect a strong entity pair match.
            # - CJK titles often do not produce useful ascii tokens, so also use
            #   a conservative full-title similarity check.
            if (len(inter) >= 2 and (sim >= threshold or strong_entity_match)) or text_sim >= 0.78:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--tz", default="Asia/Taipei")
    ap.add_argument("--max-tw", type=int, default=8)
    ap.add_argument("--max-global", type=int, default=8)
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()

    j = json.load(open(args.input, "r", encoding="utf-8"))
    regions = j.get("regions") or {}
    tw_items = (regions.get("taiwan") or {}).get("items") or []
    gl_items = (regions.get("global") or {}).get("items") or []

    # Second-stage merge to avoid "same event, many outlets" spam.
    tw_items = merge_similar_items(tw_items)
    gl_items = merge_similar_items(gl_items)

    tw = pick_taiwan_non_ai(tw_items, args.max_tw)
    gl = pick_ai_first(gl_items, args.max_global)

    now = datetime.now(ZoneInfo(args.tz)).strftime("%Y/%m/%d %H:%M")

    print(f"【財經新聞快報｜AI 優先】{now}（回顧近 5 小時｜RSS 去重）\n")

    def render_item(i: int, it: dict, region: str) -> None:
        title = display_title(it, region)
        stocks = extract_related_stocks(_body_text(it))
        stock_txt = f"（相關股票：{', '.join(stocks)}）" if stocks else ""
        print(f"{i}) **{title}**{stock_txt}")
        print(f"- 原文：[link]({it.get('link')})")
        print("")

    print(f"## 台灣（最多 {args.max_tw} 則）")
    for i, it in enumerate(tw, 1):
        render_item(i, it, "taiwan")

    print(f"## 國際（最多 {args.max_global} 則）")
    for i, it in enumerate(gl, 1):
        render_item(i, it, "global")

    errs = []
    errs.extend((regions.get("taiwan") or {}).get("errors") or [])
    errs.extend((regions.get("global") or {}).get("errors") or [])
    if args.show_errors and errs:
        print("\n### 資料來源狀態")
        for e in errs[:10]:
            print(f"- {e.get('source')}: {e.get('error')}")


if __name__ == "__main__":
    main()
