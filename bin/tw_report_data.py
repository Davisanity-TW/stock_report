#!/usr/bin/env python3
"""Fetch TWSE/TPEx public data for daily close + 3 insti net flows.

Outputs a JSON dict keyed by stock code:
{
  "2330": {
    "market": "TWSE",
    "date": "2026-01-29",
    "close": 1805.0,
    "change": -15.0,
    "pct": -0.82,
    "volume_shares": 36079326,
    "volume_lots": 36079,
    "insti": {"foreign_lots": -1234, "it_lots": 56, "dealer_lots": 78}
  },
  ...
}

Notes:
- TWSE: price/volume from STOCK_DAY; insti from T86 (ALL).
- TPEx: price/volume from tpex_mainboard_daily_close_quotes; insti from tpex_3insti_daily_trading.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import urllib.parse
import urllib.request

# Market detection:
# We'll prefer dynamic detection via TPEx close quotes (best-effort).
# If a code exists in TPEx close quotes for the day, treat it as TPEx.


def http_get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; stock_report/1.0)"
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def to_int(s: str) -> int:
    s = (s or "").strip().replace(",", "")
    if s in {"", "-", "--", "NA", "N/A"}:
        raise ValueError("empty")
    return int(float(s))


def to_float(s: str) -> float:
    s = (s or "").strip().replace(",", "")
    if s in {"", "-", "--", "NA", "N/A"}:
        raise ValueError("empty")
    return float(s)


def roc_date_str(gdate: dt.date) -> str:
    # 115/01/29
    roc_year = gdate.year - 1911
    return f"{roc_year:03d}/{gdate.month:02d}/{gdate.day:02d}"


def twse_stock_day(gdate: dt.date, code: str):
    # monthly data includes target day
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" +
        urllib.parse.urlencode({
            "date": gdate.strftime("%Y%m%d"),
            "stockNo": code,
            "response": "json",
        })
    )
    j = http_get_json(url)
    if j.get("stat") != "OK":
        raise RuntimeError(f"TWSE STOCK_DAY not OK for {code}: {j.get('stat')}")
    # find row matching target ROC date
    target = roc_date_str(gdate)
    row = None
    for r in j.get("data", []):
        if r and r[0] == target:
            row = r
            break
    if row is None:
        # fallback last row
        if j.get("data"):
            row = j["data"][-1]
        else:
            raise RuntimeError(f"TWSE STOCK_DAY empty for {code}")

    shares = to_int(row[1])
    close = to_float(row[6])
    chg = to_float(row[7])
    prev = close - chg
    pct = (chg / prev * 100.0) if prev else 0.0
    return {
        "date": gdate.isoformat(),
        "close": close,
        "change": chg,
        "pct": pct,
        "volume_shares": shares,
        "volume_lots": int(round(shares / 1000.0)),
    }


def twse_t86(gdate: dt.date):
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/T86?" +
        urllib.parse.urlencode({
            "date": gdate.strftime("%Y%m%d"),
            "selectType": "ALL",
            "response": "json",
        })
    )
    j = http_get_json(url)
    if j.get("stat") != "OK":
        raise RuntimeError(f"TWSE T86 not OK: {j.get('stat')}")
    idx = {name: i for i, name in enumerate(j.get("fields", []))}

    def get(row, field):
        i = idx.get(field)
        if i is None:
            return None
        return row[i]

    out = {}
    for r in j.get("data", []):
        code = str(r[0]).strip()
        try:
            foreign = to_int(get(r, "外陸資買賣超股數(不含外資自營商)"))
        except Exception:
            foreign = None
        try:
            it = to_int(get(r, "投信買賣超股數"))
        except Exception:
            it = None
        # dealer: use total dealer net (自營商買賣超股數)
        try:
            dealer = to_int(get(r, "自營商買賣超股數"))
        except Exception:
            dealer = None

        def to_lots(x):
            return None if x is None else int(round(x / 1000.0))

        out[code] = {
            "foreign_lots": to_lots(foreign),
            "it_lots": to_lots(it),
            "dealer_lots": to_lots(dealer),
        }
    return out


def tpex_close_quotes(gdate: dt.date):
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    rows = http_get_json(url)
    # Filter by date (115MMDD)
    roc = f"{gdate.year-1911:03d}{gdate.month:02d}{gdate.day:02d}"
    out = {}
    for r in rows:
        if r.get("Date") != roc:
            continue
        code = r.get("SecuritiesCompanyCode")
        if not code:
            continue
        try:
            close = float(str(r.get("Close", "")).strip())
        except Exception:
            close = None
        # Change sometimes has trailing spaces
        try:
            chg = float(str(r.get("Change", "")).strip())
        except Exception:
            chg = None
        try:
            shares = int(str(r.get("TradingShares", "0")).strip())
        except Exception:
            shares = None
        if close is None or chg is None or shares is None:
            continue
        prev = close - chg
        pct = (chg / prev * 100.0) if prev else 0.0
        out[code] = {
            "date": gdate.isoformat(),
            "close": close,
            "change": chg,
            "pct": pct,
            "volume_shares": shares,
            "volume_lots": int(round(shares / 1000.0)),
        }
    return out


def tpex_3insti(gdate: dt.date):
    url = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
    rows = http_get_json(url)
    roc = f"{gdate.year-1911:03d}{gdate.month:02d}{gdate.day:02d}"
    out = {}

    for r in rows:
        if r.get("Date") != roc:
            continue
        code = r.get("SecuritiesCompanyCode")
        if not code:
            continue
        # Field names are messy; use the stable ones we saw.
        def gi(key):
            try:
                return int(str(r.get(key, "")).strip())
            except Exception:
                return None

        foreign = gi("ForeignInvestorsInclude MainlandAreaInvestors-Difference")
        if foreign is None:
            foreign = gi("Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference")
        it = gi("SecuritiesInvestmentTrustCompanies-Difference")
        dealer = gi("Dealers-Difference")

        def to_lots(x):
            return None if x is None else int(round(x / 1000.0))

        out[code] = {
            "foreign_lots": to_lots(foreign),
            "it_lots": to_lots(it),
            "dealer_lots": to_lots(dealer),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--codes", required=True, help="comma-separated")
    args = ap.parse_args()

    gdate = dt.date.fromisoformat(args.date)
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    # Determine market per code (best-effort): if code appears in TPEx close quotes for the day, treat as TPEx
    # tpex_close computed above
    market_map = {c: ("TPEX" if c in tpex_close else "TWSE") for c in codes}

    twse_insti = twse_t86(gdate)
    tpex_insti = tpex_3insti(gdate)
    # tpex_close computed above

    out = {}
    for code in codes:
        market = market_map.get(code, "TWSE")
        try:
            if market == "TWSE":
                px = twse_stock_day(gdate, code)
                insti = twse_insti.get(code)
            else:
                px = tpex_close.get(code)
                if px is None:
                    raise RuntimeError("no tpex close")
                insti = tpex_insti.get(code)

            out[code] = {
                "market": market,
                **px,
                "insti": insti or {"foreign_lots": None, "it_lots": None, "dealer_lots": None},
            }
        except Exception as e:
            out[code] = {
                "market": market,
                "date": gdate.isoformat(),
                "error": str(e),
                "close": None,
                "change": None,
                "pct": None,
                "volume_shares": None,
                "volume_lots": None,
                "insti": {"foreign_lots": None, "it_lots": None, "dealer_lots": None},
            }

    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
