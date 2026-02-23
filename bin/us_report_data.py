#!/usr/bin/env python3
"""Fetch US market daily close data (free sources).

- Equities/ETFs: Stooq daily CSV
  https://stooq.com/q/d/l/?s=qqq.us&i=d

- VIX: CBOE daily history CSV
  https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv

Outputs JSON to stdout.

Note: Date logic is intentionally simple. The caller can pass --date, or omit
and let the script pick "latest available" from each source.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo


STOOQ_BASE = "https://stooq.com/q/d/l/?i=d&s="
VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"


@dataclass
class Bar:
    date: str
    close: float
    prev_close: float | None = None
    volume: int | None = None

    @property
    def chg(self):
        if self.prev_close is None:
            return None
        return self.close - self.prev_close

    @property
    def chg_pct(self):
        if self.prev_close in (None, 0):
            return None
        return (self.close / self.prev_close - 1.0) * 100.0


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "clawdbot/stock_report"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_stooq(symbol: str, wanted_date: str | None) -> Bar | None:
    # symbol must be like qqq.us
    text = _http_get(STOOQ_BASE + symbol)
    if text.strip().startswith("No data"):
        return None
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        return None

    # Pick row: wanted_date if present else last row.
    idx = None
    if wanted_date:
        for i, r in enumerate(rows):
            if r.get("Date") == wanted_date:
                idx = i
                break
    if idx is None:
        idx = len(rows) - 1

    r = rows[idx]
    close = float(r["Close"])
    vol = r.get("Volume")
    volume = int(float(vol)) if vol not in (None, "") else None

    prev_close = None
    if idx - 1 >= 0:
        prev_close = float(rows[idx - 1]["Close"])

    return Bar(date=r["Date"], close=close, prev_close=prev_close, volume=volume)


def _parse_cboe_vix(wanted_date: str | None) -> Bar | None:
    text = _http_get(VIX_URL)
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        return None

    # Column names: DATE, OPEN, HIGH, LOW, CLOSE
    # Find wanted_date else last row.
    idx = None
    if wanted_date:
        for i, r in enumerate(rows):
            if r.get("DATE") == wanted_date:
                idx = i
                break
    if idx is None:
        idx = len(rows) - 1

    r = rows[idx]
    close = float(r["CLOSE"])
    prev_close = float(rows[idx - 1]["CLOSE"]) if idx - 1 >= 0 else None
    return Bar(date=r["DATE"], close=close, prev_close=prev_close, volume=None)


def default_trade_date_et() -> str:
    """Return ET calendar date string for 'latest available' close.

    At Asia/Taipei 06:xx, ET is usually ~17:xx previous day, i.e. market has
    already closed for that ET date.

    We do a simple weekend shift; US holidays are not handled.
    """
    now_et = dt.datetime.now(ZoneInfo("America/New_York"))
    d = now_et.date()
    # If weekend, shift back to Friday.
    if d.weekday() == 5:  # Sat
        d = d - dt.timedelta(days=1)
    elif d.weekday() == 6:  # Sun
        d = d - dt.timedelta(days=2)
    return d.isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Wanted trade date (YYYY-MM-DD). If omitted, use ET date and latest available per source.")
    ap.add_argument("--tickers", default="QQQ,NVDA,AMD,QCOM,MRVL,TSLA,GOOG,AAPL,SNDK,MU,AVGO,PLTR,INTC",
                    help="Comma-separated US tickers")
    args = ap.parse_args()

    wanted_date = args.date or default_trade_date_et()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    # Stooq uses lowercase and .us suffix for US stocks
    def stooq_sym(t: str) -> str:
        # Some tickers may be non-standard; still try.
        return t.lower() + ".us"

    out = {
        "asof_date": wanted_date,
        "source": {
            "stooq": "stooq.com",
            "vix": VIX_URL,
        },
        "tickers": {},
        "indicators": {},
    }

    for t in tickers:
        bar = _parse_stooq(stooq_sym(t), wanted_date)
        if bar is None:
            out["tickers"][t] = {"ok": False, "error": "no data"}
            continue
        out["tickers"][t] = {
            "ok": True,
            "date": bar.date,
            "close": bar.close,
            "chg": bar.chg,
            "chg_pct": bar.chg_pct,
            "volume": bar.volume,
        }

    # VIX
    vix_bar = _parse_cboe_vix(wanted_date)
    if vix_bar is None:
        out["indicators"]["VIX"] = {"ok": False, "error": "no data"}
    else:
        out["indicators"]["VIX"] = {
            "ok": True,
            "date": vix_bar.date,
            "close": vix_bar.close,
            "chg": vix_bar.chg,
            "chg_pct": vix_bar.chg_pct,
        }

    # Gold/Silver/BTC from Stooq (as spot series)
    for name, sym in [("XAUUSD", "xauusd"), ("XAGUSD", "xagusd"), ("BTCUSD", "btcusd")]:
        bar = _parse_stooq(sym, wanted_date)
        if bar is None:
            out["indicators"][name] = {"ok": False, "error": "no data"}
        else:
            out["indicators"][name] = {
                "ok": True,
                "date": bar.date,
                "close": bar.close,
                "chg": bar.chg,
                "chg_pct": bar.chg_pct,
            }

    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
