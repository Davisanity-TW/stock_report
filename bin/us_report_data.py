#!/usr/bin/env python3
"""Fetch US market daily close data (free sources).

- Equities/ETFs + spot proxies (gold/silver/btc): Stooq quote CSV
  https://stooq.com/q/l/?f=sd2t2ohlcvp&h&e=csv&s=qqq.us

- VIX: CBOE daily history CSV
  https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv

Outputs JSON to stdout.

Note: Some environments (notably AWS) observe Stooq returning HTTP 200 with an
empty body. We retry those URLs via r.jina.ai proxy and extract the
"Markdown Content:" section.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# NOTE: Stooq daily history endpoint (/q/d/l) may return empty responses from some hosts.
# We use the quote endpoint (/q/l) which also provides Prev close.
STOOQ_QUOTE_BASE = "https://stooq.com/q/l/?f=sd2t2ohlcvp&h&e=csv&s="
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


def _http_get(url: str, timeout: int = 12) -> str:
    """HTTP GET.

    For Stooq URLs we *prefer* going through r.jina.ai, because some hosts see
    HTTP 200 + empty body from stooq.com.
    """

    def _fetch(u: str) -> str:
        req = urllib.request.Request(u, headers={"User-Agent": "clawdbot/stock_report"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _unwrap_jina(wrapped: str) -> str:
        if "Markdown Content:" in wrapped:
            return wrapped.split("Markdown Content:", 1)[1].lstrip()
        return wrapped

    # Stooq: go via proxy first
    if url.startswith("https://stooq.com/"):
        try:
            return _unwrap_jina(_fetch("https://r.jina.ai/" + url))
        except Exception:
            pass

    # Default: direct then fallback
    text = _fetch(url)
    if text.strip():
        return text

    try:
        return _unwrap_jina(_fetch("https://r.jina.ai/" + url))
    except Exception:
        return text


def _parse_stooq(symbol: str, wanted_date: str | None) -> Bar | None:
    """Fetch one Stooq quote row.

    symbol examples: qqq.us, nvda.us, xauusd, btcusd
    """
    # Stooq sometimes returns placeholder N/D intermittently; retry a couple times.
    text = ""
    for i in range(3):
        text = _http_get(STOOQ_QUOTE_BASE + symbol)
        if text.strip() and not text.strip().startswith("No data") and "N/D" not in text:
            break
        if i < 2:
            time.sleep(0.4)
    if not text.strip() or text.strip().startswith("No data"):
        return None

    # Normalize line endings; some proxies return CRLF.
    rows = list(csv.DictReader(text.replace("\r", "").splitlines()))
    if not rows:
        return None

    r = rows[0]
    if (r.get("Close") or "").strip().upper() in {"", "N/A", "NA", "N/D"}:
        return None

    close = float(r["Close"])

    prev_close = None
    prev = (r.get("Prev") or "").strip()
    if prev and prev.upper() not in {"N/A", "NA", "N/D"}:
        prev_close = float(prev)

    volume = None
    vol = (r.get("Volume") or "").strip()
    if vol and vol.upper() not in {"N/A", "NA", "N/D"}:
        volume = int(float(vol))

    return Bar(date=r.get("Date") or (wanted_date or ""), close=close, prev_close=prev_close, volume=volume)


def _parse_cboe_vix(wanted_date: str | None) -> Bar | None:
    text = _http_get(VIX_URL, timeout=20)
    # Normalize line endings.
    rows = list(csv.DictReader(text.replace("\r", "").splitlines()))
    if not rows:
        return None

    # Column names: DATE, OPEN, HIGH, LOW, CLOSE
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
    """Return ET calendar date string for 'latest available' close (weekend-adjusted)."""
    now_et = dt.datetime.now(ZoneInfo("America/New_York"))
    d = now_et.date()
    if d.weekday() == 5:  # Sat
        d = d - dt.timedelta(days=1)
    elif d.weekday() == 6:  # Sun
        d = d - dt.timedelta(days=2)
    return d.isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Wanted trade date (YYYY-MM-DD). If omitted, use ET date and latest available per source.")
    ap.add_argument(
        "--tickers",
        default="QQQ,NVDA,AMD,QCOM,MRVL,TSLA,GOOG,AAPL,SNDK,MU,AVGO,PLTR,INTC",
        help="Comma-separated US tickers",
    )
    args = ap.parse_args()

    wanted_date = args.date or default_trade_date_et()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    def stooq_sym(t: str) -> str:
        return t.lower() + ".us"

    out = {
        "asof_date": wanted_date,
        "source": {"stooq": "stooq.com", "vix": VIX_URL},
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
