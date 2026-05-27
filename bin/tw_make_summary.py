#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate TW close summary markdown from cached JSON.

Inputs are produced by:
- tmp/tw-index.json (TWSE afterTrading/FMTQIK parsed)
- tmp/tw-data.json (bin/tw_report_data.py)
- optional news JSON from bin/finance_news_collect.py

This script is intentionally deterministic and API-key free.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return {"error": f"missing_or_empty:{path}"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"json_parse_failed:{path}:{e}"}


def _fmt_num(x):
    if x is None:
        return "NA"
    return str(x)


def _to_float_maybe(x):
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", "")
        s = re.sub(r"<[^>]+>", "", s)
        if s in {"", "-", "--", "NA", "N/A"}:
            return None
        return float(s)
    except Exception:
        return None


def _weekday_en(date_str: str) -> str:
    d = dt.date.fromisoformat(date_str)
    return d.strftime("%a")


def _iter_items(data: dict):
    """Yield normalized item dicts.

    Supports two cache shapes:
    1) Newer: {"items": [{code,name,change_pct,volume,inst_*}, ...]}
    2) Current tw_report_data.py output: {"2330": {close,pct,volume_lots,insti{...}}, ...}
    """
    if not isinstance(data, dict):
        return
    items = data.get("items")
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                yield it
        return

    # dict keyed by code
    for code, r in data.items():
        if code == "items":
            continue
        if not isinstance(r, dict):
            continue
        insti = r.get("insti") or {}
        yield {
            "code": code,
            "name": r.get("name"),
            "change_pct": r.get("pct"),
            "volume": r.get("volume_lots"),
            "inst_foreign": insti.get("foreign_lots"),
            "inst_investment_trust": insti.get("it_lots"),
            "inst_dealer": insti.get("dealer_lots"),
        }


def _sum_inst(data: dict, key: str):
    total = 0
    ok = False
    for it in _iter_items(data):
        v = it.get(key)
        if isinstance(v, (int, float)):
            total += v
            ok = True
    return total if ok else None


TW_NEWS_KEYWORDS = [
    "台股", "台灣股市", "上市", "上櫃", "加權指數", "櫃買", "集中市場", "權值股",
    "半導體", "電子股", "AI", "人工智慧", "伺服器", "先進封裝", "CoWoS", "ASIC",
    "PCB", "CCL", "散熱", "光通訊", "矽光子", "CPO", "記憶體", "被動元件", "法說",
    "營收", "財報", "外資", "投信", "自營商", "三大法人", "買超", "賣超", "目標價",
]

TW_NEWS_BLOCKLIST = [
    "發票", "長照", "土地公告", "地上權", "三陰性乳癌", "核談判", "荷姆茲", "日本股市",
]


def _news_score(it: dict) -> int:
    text = " ".join(str(it.get(k) or "") for k in ("title", "raw_summary", "source", "source_id"))
    score = 0
    for kw in TW_NEWS_KEYWORDS:
        if kw.lower() in text.lower():
            score += 2
    if re.search(r"\b\d{4}\b", text):
        score += 2
    source_id = str(it.get("source_id") or "")
    if "tw_market" in source_id:
        score += 4
    if "google_news_tw" in source_id:
        score += 3
    if "cna" in source_id:
        score += 2
    for bad in TW_NEWS_BLOCKLIST:
        if bad in text:
            score -= 5
    if "公告" in text and not any(k in text for k in ("法說", "營收", "財報", "股利", "併購", "投資", "擴廠")):
        score -= 3
    return score


def _news_norm_title(title: str) -> str:
    t = re.sub(r"\s+", "", title or "").lower()
    t = re.split(r"[-｜|－]", t)[0]
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t[:36]


def _pick_tw_news(news: dict, limit: int = 6):
    items = (((news.get("regions") or {}).get("taiwan") or {}).get("items") or [])
    out = []
    seen_titles: set[str] = set()
    ranked = sorted(items, key=lambda it: (_news_score(it), it.get("published_at") or ""), reverse=True)
    for it in ranked:
        title = (it.get("title") or "").strip()
        link = (it.get("link") or "").strip()
        source = (it.get("source") or "").strip()
        if not title or not link:
            continue
        nt = _news_norm_title(title)
        if nt and nt in seen_titles:
            continue
        if _news_score(it) <= 0 and out:
            continue
        out.append((title, link, source))
        if nt:
            seen_titles.add(nt)
        if len(out) >= limit:
            break
    return out


def _http_json(url: str, timeout: int = 25):
    last_exc = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; stock_report/1.0)"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_exc = e
            if attempt < 2:
                time.sleep(1 + attempt)
    raise last_exc


def _roc_compact(gdate: dt.date) -> str:
    return f"{gdate.year - 1911:03d}{gdate.month:02d}{gdate.day:02d}"


def _twse_mi_index(gdate: dt.date) -> dict:
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?" + urllib.parse.urlencode(
        {"date": gdate.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"}
    )
    return _http_json(url)


def _parse_twse_quotes(mi: dict) -> dict[str, dict]:
    quotes: dict[str, dict] = {}
    tables = mi.get("tables") or []
    for table in tables:
        fields = table.get("fields") or []
        if not fields or fields[0] != "證券代號":
            continue
        idx = {name: i for i, name in enumerate(fields)}
        for row in table.get("data") or []:
            if not isinstance(row, list) or len(row) < len(fields):
                continue
            code = str(row[idx.get("證券代號", 0)]).strip()
            if not re.fullmatch(r"\d{4}", code):
                continue
            close = _to_float_maybe(row[idx.get("收盤價")])
            chg = _to_float_maybe(row[idx.get("漲跌價差")])
            vol = _to_float_maybe(row[idx.get("成交股數")])
            if close is None or chg is None:
                continue
            prev = close - chg
            pct = (chg / prev * 100.0) if prev else 0.0
            quotes[code] = {
                "code": code,
                "name": str(row[idx.get("證券名稱", 1)]).strip().rstrip("*"),
                "pct": pct,
                "volume_lots": int(round((vol or 0) / 1000.0)),
                "market": "TWSE",
            }
    return quotes


def _parse_twse_sector_indices(mi: dict) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for table in (mi.get("tables") or [])[:2]:
        fields = table.get("fields") or []
        if not fields or fields[0] != "指數":
            continue
        idx_name = fields.index("指數")
        idx_pct = fields.index("漲跌百分比(%)") if "漲跌百分比(%)" in fields else None
        if idx_pct is None:
            continue
        for row in table.get("data") or []:
            if not isinstance(row, list) or len(row) <= idx_pct:
                continue
            name = str(row[idx_name]).strip()
            if "類指數" not in name:
                continue
            pct = _to_float_maybe(row[idx_pct])
            if pct is None:
                continue
            clean = name.replace("類指數", "")
            rows.append((clean, pct))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def _parse_tpex_quotes(gdate: dt.date) -> dict[str, dict]:
    rows = _http_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
    target = _roc_compact(gdate)
    out: dict[str, dict] = {}
    for row in rows:
        if row.get("Date") != target:
            continue
        code = str(row.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        close = _to_float_maybe(row.get("Close"))
        chg = _to_float_maybe(row.get("Change"))
        vol = _to_float_maybe(row.get("TradingShares"))
        if close is None or chg is None:
            continue
        prev = close - chg
        pct = (chg / prev * 100.0) if prev else 0.0
        out[code] = {
            "code": code,
            "name": str(row.get("CompanyName") or "").strip().rstrip("*"),
            "pct": pct,
            "volume_lots": int(round((vol or 0) / 1000.0)),
            "market": "TPEX",
        }
    return out


THEME_BASKETS = {
    "AI伺服器/ODM": ["2382", "3231", "6669", "2356", "2317", "2376", "2357"],
    "散熱/機殼": ["3017", "3324", "3653", "6230", "8210", "8996", "3338"],
    "光通訊/CPO": ["4979", "3163", "3363", "3234", "3081", "6442", "3450", "4908", "8011"],
    "半導體/ASIC/封測": ["2330", "2454", "3661", "3443", "3035", "5274", "2449", "3711", "3264"],
    "記憶體/儲存": ["2344", "2408", "2337", "8299", "6770", "3260"],
    "PCB/CCL": ["2383", "2368", "6274", "6213", "3037", "4958", "3044"],
    "電源/被動元件": ["2308", "2327", "2492", "6173", "6284", "6449"],
    "網通/交換器": ["2345", "6285", "5388", "3596", "4906", "2412"],
}


def _fmt_pct(pct: float) -> str:
    return f"{pct:+.2f}%"


def _name_pct(name: str, pct: float) -> str:
    return f"{name}({_fmt_pct(pct)})"


def _theme_rotation(day: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    quotes: dict[str, dict] = {}
    sectors: list[tuple[str, float]] = []

    try:
        gdate = dt.date.fromisoformat(day)
        mi = _twse_mi_index(gdate)
        quotes = _parse_twse_quotes(mi)
        sectors = _parse_twse_sector_indices(mi)
    except Exception as e:
        errors.append(f"TWSE 公開行情抓取失敗：{e}")

    try:
        if "gdate" not in locals():
            gdate = dt.date.fromisoformat(day)
        quotes.update(_parse_tpex_quotes(gdate))
    except Exception as e:
        errors.append(f"TPEx 公開行情抓取失敗：{e}")

    sector_lines = []
    if sectors:
        top = "、".join(_name_pct(name, pct) for name, pct in sectors[:5])
        weak = "、".join(_name_pct(name, pct) for name, pct in sorted(sectors, key=lambda x: x[1])[:3])
        sector_lines.append(f"- 強勢類股：{top}。")
        sector_lines.append(f"- 落後類股：{weak}。")
    elif errors:
        sector_lines.extend(f"- {e}" for e in errors)

    theme_rows = []
    for theme, codes in THEME_BASKETS.items():
        members = [quotes[c] for c in codes if c in quotes and isinstance(quotes[c].get("pct"), (int, float))]
        if len(members) < 2:
            continue
        avg = sum(m["pct"] for m in members) / len(members)
        adv = sum(1 for m in members if m["pct"] > 0)
        reps = sorted(members, key=lambda m: (m["pct"], m.get("volume_lots") or 0), reverse=True)[:3]
        rep_txt = "、".join(f"{m['name']}({m['code']}) {m['pct']:+.2f}%" for m in reps)
        theme_rows.append((avg, adv, len(members), theme, rep_txt))
    theme_rows.sort(reverse=True, key=lambda x: (x[0], x[1] / x[2]))

    theme_lines = []
    if theme_rows:
        theme_lines.append(
            "- 強勢主題："
            + "、".join(_name_pct(theme, avg) for avg, _adv, _total, theme, _rep_txt in theme_rows[:5])
            + "。"
        )
        theme_lines.append("- 主題細節（等權平均；TWSE/TPEx 收盤行情）：")
        theme_lines.extend(
            f"  - {theme}：平均 {_fmt_pct(avg)}，上漲 {adv}/{total}；代表：{rep_txt}"
            for avg, adv, total, theme, rep_txt in theme_rows[:5]
        )
    elif errors and not sector_lines:
        theme_lines.extend(f"- {e}" for e in errors)
    return sector_lines, theme_lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=False, help="YYYY-MM-DD (Asia/Taipei). Defaults to today in Asia/Taipei")
    ap.add_argument("--index", default="tmp/tw-index.json")
    ap.add_argument("--data", default="tmp/tw-data.json")
    ap.add_argument("--news", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tz = ZoneInfo("Asia/Taipei")
    day = args.date or dt.datetime.now(tz).date().isoformat()

    idx = _load_json(args.index)
    data = _load_json(args.data)

    # Index numbers
    # We support two cache formats:
    # (A) flattened: {close, change, change_pct}
    # (B) raw wrapper: {data:{fields:[...], data:[[...], ...]}} from TWSE FMTQIK

    def _roc_date_str(gdate: dt.date) -> str:
        roc_year = gdate.year - 1911
        return f"{roc_year:03d}/{gdate.month:02d}/{gdate.day:02d}"

    def _parse_fmtqik(cache: dict, day_str: str):
        """Best-effort parse for TWSE afterTrading/FMTQIK response.

        We accept multiple cache shapes:
        - Direct TWSE payload: {"fields": [...], "data": [[...], ...]}
        - TWSE wrapper: {"data": {"fields": [...], "data": [[...], ...]}}
        - Our fetch wrapper: {"ok": true, "payload": <TWSE payload>}

        TWSE fields should include:
          - "日期"
          - "發行量加權股價指數"
          - "漲跌點數"
        """
        try:
            gdate = dt.date.fromisoformat(day_str)
        except Exception:
            return None, None, None, "bad_date"

        if not isinstance(cache, dict):
            return None, None, None, "missing:data"

        # Unwrap our fetch wrapper if present
        if isinstance(cache.get("payload"), dict):
            cache = cache["payload"]

        # Two shapes seen in the wild:
        # 1) raw: {stat, fields:[...], data:[[...]]}
        # 2) wrapped: {data:{fields:[...], data:[[...]]}}
        if isinstance(cache.get("fields"), list) and isinstance(cache.get("data"), list):
            fields = cache.get("fields") or []
            rows = cache.get("data") or []
        else:
            wrapper = cache.get("data")
            if not isinstance(wrapper, dict):
                return None, None, None, "missing:data"
            fields = wrapper.get("fields") or []
            rows = wrapper.get("data") or []
        if not isinstance(fields, list) or not isinstance(rows, list):
            return None, None, None, "bad_schema"

        # Find column indices
        try:
            i_date = fields.index("日期")
            i_close = fields.index("發行量加權股價指數")
            i_chg = fields.index("漲跌點數")
        except ValueError:
            return None, None, None, "missing_fields"

        target = _roc_date_str(gdate)
        row = None
        for r in rows:
            if isinstance(r, list) and len(r) > max(i_date, i_close, i_chg) and str(r[i_date]).strip() == target:
                row = r
                break
        # Fallback: use the last row (usually the latest trading day) if exact match not found
        if row is None and rows:
            r = rows[-1]
            if isinstance(r, list) and len(r) > max(i_date, i_close, i_chg):
                row = r

        if row is None:
            return None, None, None, "row_not_found"

        close = _to_float_maybe(row[i_close])
        chg = _to_float_maybe(row[i_chg])
        if close is None or chg is None:
            return None, None, None, "parse_failed"

        prev = close - chg
        chgp = (chg / prev * 100.0) if prev else 0.0
        return close, chg, chgp, None

    close = _to_float_maybe(idx.get("close"))
    chg = _to_float_maybe(idx.get("change"))
    chgp = _to_float_maybe(idx.get("change_pct"))
    idx_err = idx.get("error")

    if close is None or chg is None or chgp is None:
        c2, d2, p2, err2 = _parse_fmtqik(idx, day)
        if c2 is not None and d2 is not None and p2 is not None:
            close, chg, chgp = c2, d2, p2
        else:
            idx_err = idx_err or err2 or "資料不足"

    if close is None or chg is None or chgp is None:
        idx_line = f"- 大盤（加權指數）：NA（{idx_err or '資料不足'}）。"
    else:
        # keep sign in change_pct if present
        idx_line = f"- 大盤（加權指數）：收 {close:,.2f} 點，{chg:+g} 點（{chgp:+.2f}%）。"

    # Institutions: sums over watchlist items only
    f_sum = _sum_inst(data, "inst_foreign")
    it_sum = _sum_inst(data, "inst_investment_trust")
    d_sum = _sum_inst(data, "inst_dealer")

    def _inst_line(label: str, v):
        if v is None:
            return f"- {label}：NA（追蹤清單彙總仍多為 NA；可能為來源尚未更新或抓取失敗）"
        return f"- {label}（追蹤清單合計）：{int(v):,} 張"

    # News
    news_block = []
    if args.news:
        news = _load_json(args.news)
        picked = _pick_tw_news(news, limit=8)
        if picked:
            for title, link, source in picked:
                sfx = f"（{source}）" if source else ""
                news_block.append(f"- {title}{sfx} [link]({link})")

    if not news_block:
        news_block = [
            "- （資料不足：本次未取得可用新聞清單；先附官方資料連結，後續可再擴充新聞來源。）",
            "  - TWSE 個股日成交資訊：https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
            "  - TWSE 三大法人（個股，T86）：https://www.twse.com.tw/rwd/zh/fund/T86",
            "  - TPEx 上櫃收盤行情：https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            "  - TPEx 三大法人：https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading",
        ]

    sector_lines, theme_lines = _theme_rotation(day)

    # Potential strength list: take top movers among items that have change_pct
    # Minimal mapping for names (fallback)
    NAME_MAP = {
        "0050": "元大台灣50",
        "00631L": "元大台灣50正2",
        "2330": "台積電",
        "2454": "聯發科",
        "2317": "鴻海",
        "2308": "台達電",
        "8299": "群聯",
        "6669": "緯穎",
        "2344": "華邦電",
        "2327": "國巨",
        "2449": "京元電子",
        "2357": "華碩",
        "3017": "奇鋐",
        "2408": "南亞科",
        "2337": "旺宏",
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

    movers = []
    for it in _iter_items(data):
        code = it.get("code")
        name = it.get("name") or (NAME_MAP.get(code) if code else None)
        cp = it.get("change_pct")
        vol = it.get("volume")
        if isinstance(cp, (int, float)) and code and name:
            movers.append((cp, vol if isinstance(vol, (int, float)) else None, code, name))
    movers.sort(reverse=True, key=lambda x: x[0])
    top = movers[:6]
    top_lines = []
    for cp, vol, code, name in top:
        vtxt = f"，量 {int(vol):,} 張" if isinstance(vol, (int, float)) else ""
        top_lines.append(f"  - {name}({code})：{cp:+.2f}%{vtxt}")

    md = []
    md.append(f"## {day} ({_weekday_en(day)})")
    md.append("")
    md.append("### A) 今日盤勢與族群輪動（觀察重點)")
    md.append(idx_line)
    if top_lines:
        md.append("- 追蹤清單中相對強勢（依漲跌幅排序；僅供盤後整理，需再搭配量能/線型確認）：")
        md.extend(top_lines)
    else:
        md.append("- 追蹤清單：目前漲跌幅資料不足（多為 NA），先保留框架，待來源補齊再更新。")

    md.append("")
    md.append("### B) 三大法人動向")
    md.append(_inst_line("外資", f_sum))
    md.append(_inst_line("投信", it_sum))
    md.append(_inst_line("自營商", d_sum))
    md.append("- 註：此處為『追蹤清單合計』，非全市場總和；若要全市場需另抓交易所彙總資料。")

    md.append("")
    md.append("### V) 重要新聞 / 事件（4-8 則，附連結)")
    md.extend(news_block)

    md.append("")
    md.append("### D) 潛在轉強名單（需隔日用K線確認)")
    if top_lines:
        md.append("- 初步候選（以今日相對強勢/量能為線索，隔日需再確認均線結構與量能延續）：")
        for cp, vol, code, name in top[:5]:
            md.append(f"  - {name}({code})")
    else:
        md.append("- （資料不足：清單內缺乏完整量價/法人資訊，暫不做轉強篩選。）")

    md.append("")
    md.append("### E) 族群輪動觀察（公開行情計算）")
    md.extend(sector_lines or ["- TWSE 類股指數：資料不足。"])
    if theme_lines:
        md.extend(theme_lines)
    else:
        md.append("- 主題籃子：資料不足。")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
