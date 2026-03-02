#!/usr/bin/env python3
"""
Batch download China A-share data for 3-year low research.

Uses Yahoo Finance (yfinance) for all data access. AKShare was previously
used but is unreliable from overseas (East Money blocks non-China IPs).

Strategy:
1. Use a curated list of major A-share tickers + DB-stored tickers
2. Fetch current quote data via yfinance
3. Pre-filter: keep only stocks where current price <= 70% of 52-week high
4. For pre-filtered candidates, download full 3-year price history
5. Store everything in SQLite

Usage:
    python batch_cn_download.py --step spot       # Step 1: Download spot data + save stocks
    python batch_cn_download.py --step prefilter   # Step 2: Pre-filter candidates
    python batch_cn_download.py --step history     # Step 3: Download 3yr history for candidates
    python batch_cn_download.py --step all         # Run all steps
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "db_ops"))
from db_manager import get_connection, DB_PATH
from stock_ops import bulk_add_stocks
from price_ops import bulk_upsert_prices


# Major China A-share tickers for batch scanning
# Shanghai (SSE): .SS suffix | Shenzhen (SZSE): .SZ suffix
_CN_MAJOR_TICKERS = [
    # SSE 50 representative stocks
    "600519", "601318", "600036", "600900", "601398",
    "600276", "600030", "601012", "601888", "600309",
    "600585", "601166", "601288", "600887", "601601",
    "600048", "601668", "600809", "601328", "600690",
    "601919", "600016", "600000", "601857", "601088",
    "600028", "601628", "601939", "600837", "601138",
    "600031", "600104", "601186", "600436", "601211",
    "600406", "601225", "601995", "603259", "603501",
    "603288", "603993", "603986", "600763", "600089",
    # SZSE representative stocks
    "000858", "000333", "000001", "002594", "002415",
    "000651", "000002", "002304", "000568", "000725",
    "002142", "000661", "002352", "002475", "000538",
    "002714", "000063", "002230", "000338", "002027",
    "002032", "000776", "002049", "000895", "000876",
    # ChiNext (创业板) representative stocks
    "300750", "300059", "300760", "300124", "300015",
    "300274", "300122", "300033", "300408", "300347",
    "300529", "300782", "300661", "300316", "300142",
]


def _yf_ticker(ticker: str) -> str:
    """Convert 6-digit ticker to yfinance format."""
    if ticker.startswith("6"):
        return f"{ticker}.SS"
    else:
        return f"{ticker}.SZ"


def _get_all_tickers() -> list[str]:
    """Get combined ticker list from hardcoded + DB."""
    tickers = set(_CN_MAJOR_TICKERS)

    # Add tickers from DB
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT ticker FROM stocks WHERE market = 'CN'"
        ).fetchall()
        conn.close()
        for row in rows:
            tickers.add(row[0])
    except Exception:
        pass

    return sorted(tickers)


def _fetch_with_retry(fetch_fn, max_attempts=3, base_delay=5):
    """Retry a fetch function with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return fetch_fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"  Attempt {attempt+1}/{max_attempts} failed ({e.__class__.__name__}), retrying in {delay}s...")
            time.sleep(delay)


def step_spot():
    """Step 1: Fetch quote data for all known CN tickers via yfinance."""
    print("=" * 60)
    print("Step 1: Fetching China A-share data via Yahoo Finance...")
    print("=" * 60)

    tickers = _get_all_tickers()
    print(f"Total tickers to scan: {len(tickers)}")

    # Batch download using yfinance (downloads multiple tickers at once)
    yf_tickers = [_yf_ticker(t) for t in tickers]

    # Process in batches of 50 to avoid timeout
    batch_size = 50
    stocks = []
    records = []
    prefilter_data = []

    for batch_start in range(0, len(yf_tickers), batch_size):
        batch = yf_tickers[batch_start:batch_start + batch_size]
        batch_raw = tickers[batch_start:batch_start + batch_size]
        print(f"  Batch {batch_start // batch_size + 1}: downloading {len(batch)} tickers...")

        try:
            data = yf.download(batch, period="5d", group_by="ticker", progress=False, threads=True)
        except Exception as e:
            print(f"  Batch download failed: {e}")
            continue

        for i, yf_t in enumerate(batch):
            raw_ticker = batch_raw[i]
            try:
                if len(batch) == 1:
                    ticker_data = data
                else:
                    ticker_data = data[yf_t] if yf_t in data.columns.get_level_values(0) else None

                if ticker_data is None or ticker_data.empty:
                    continue

                last_row = ticker_data.dropna(how="all").iloc[-1]
                close_price = float(last_row["Close"])
                if close_price <= 0:
                    continue

                # Get company info for name
                stock_obj = yf.Ticker(yf_t)
                info = stock_obj.info
                name = info.get("shortName", raw_ticker)

                stocks.append({
                    "ticker": raw_ticker,
                    "market": "CN",
                    "name": name,
                    "exchange": "SSE" if raw_ticker.startswith("6") else "SZSE",
                    "currency": "CNY",
                })

                records.append({
                    "ticker": raw_ticker,
                    "market": "CN",
                    "date": last_row.name.strftime("%Y-%m-%d") if hasattr(last_row.name, "strftime") else datetime.now().strftime("%Y-%m-%d"),
                    "open": float(last_row["Open"]) if last_row["Open"] else None,
                    "high": float(last_row["High"]) if last_row["High"] else None,
                    "low": float(last_row["Low"]) if last_row["Low"] else None,
                    "close": close_price,
                    "volume": int(last_row["Volume"]) if last_row["Volume"] else None,
                })

                high_52w = info.get("fiftyTwoWeekHigh")
                low_52w = info.get("fiftyTwoWeekLow")

                prefilter_data.append({
                    "ticker": raw_ticker,
                    "name": name,
                    "price": close_price,
                    "high_52w": high_52w,
                    "low_52w": low_52w,
                    "volume": info.get("volume", 0),
                    "market_cap": info.get("marketCap"),
                })

            except Exception as e:
                print(f"  Skip {raw_ticker}: {e}")
                continue

        # Rate limit between batches
        time.sleep(1)

    # Save to DB
    if stocks:
        count = bulk_add_stocks(stocks)
        print(f"Saved {count} stocks to database")

    if records:
        price_count = bulk_upsert_prices(records)
        print(f"Saved {price_count} spot prices to database")

    # Save prefilter data
    temp_path = os.path.join(os.path.dirname(__file__), "_cn_spot_data.json")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(prefilter_data, f, ensure_ascii=False, indent=2)
    print(f"Spot data saved to {temp_path} ({len(prefilter_data)} stocks)")

    return prefilter_data


def step_prefilter():
    """Step 2: Pre-filter stocks where current price <= 70% of 52-week high."""
    print("=" * 60)
    print("Step 2: Pre-filtering candidates (price <= 70% of 52-week high)...")
    print("=" * 60)

    temp_path = os.path.join(os.path.dirname(__file__), "_cn_spot_data.json")
    with open(temp_path, "r", encoding="utf-8") as f:
        spot_data = json.load(f)

    candidates = []
    skipped_no_52w = 0
    skipped_above_threshold = 0
    skipped_low_volume = 0

    for stock in spot_data:
        high_52w = stock["high_52w"]
        price = stock["price"]
        volume = stock["volume"]

        if not high_52w or high_52w <= 0:
            skipped_no_52w += 1
            continue

        if volume < 10000:
            skipped_low_volume += 1
            continue

        pct_of_high = (price / high_52w) * 100

        if pct_of_high <= 70:
            stock["pct_of_52w_high"] = round(pct_of_high, 1)
            candidates.append(stock)
        else:
            skipped_above_threshold += 1

    candidates.sort(key=lambda x: x["pct_of_52w_high"])

    print(f"Total stocks: {len(spot_data)}")
    print(f"Skipped (no 52w data): {skipped_no_52w}")
    print(f"Skipped (low volume): {skipped_low_volume}")
    print(f"Skipped (above 70% threshold): {skipped_above_threshold}")
    print(f"Pre-filter candidates: {len(candidates)}")

    candidates_path = os.path.join(os.path.dirname(__file__), "_cn_candidates.json")
    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"Candidates saved to {candidates_path}")

    print(f"\nTop 20 most beaten down (by 52-week high):")
    print(f"{'Ticker':<8} {'Name':<12} {'Price':>8} {'52wH':>8} {'%ofHigh':>8}")
    print("-" * 50)
    for c in candidates[:20]:
        print(f"{c['ticker']:<8} {c['name'][:10]:<12} {c['price']:>8.2f} {c['high_52w']:>8.2f} {c['pct_of_52w_high']:>7.1f}%")

    return candidates


def step_history(max_stocks=None):
    """Step 3: Download 3-year price history for pre-filtered candidates."""
    print("=" * 60)
    print("Step 3: Downloading 3-year price history for candidates...")
    print("=" * 60)

    candidates_path = os.path.join(os.path.dirname(__file__), "_cn_candidates.json")
    with open(candidates_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    if max_stocks:
        candidates = candidates[:max_stocks]

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d")

    total = len(candidates)
    success = 0
    errors = 0
    total_records = 0

    print(f"Downloading history for {total} stocks ({start_date} to {end_date})...")

    for i, stock in enumerate(candidates):
        ticker = stock["ticker"]
        yf_t = _yf_ticker(ticker)
        try:
            stock_obj = yf.Ticker(yf_t)
            df = stock_obj.history(start=start_date, end=end_date)

            if df.empty:
                errors += 1
                continue

            records = []
            for date, row in df.iterrows():
                records.append({
                    "ticker": ticker,
                    "market": "CN",
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]),
                })

            bulk_upsert_prices(records)
            success += 1
            total_records += len(records)

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error {ticker}: {e}")

        # Progress + rate limiting
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{total} ({success} ok, {errors} err, {total_records} records)")
            time.sleep(2)
        elif (i + 1) % 10 == 0:
            time.sleep(0.5)

    print(f"\nDone: {success}/{total} stocks downloaded, {errors} errors")
    print(f"Total price records: {total_records}")

    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM daily_prices WHERE market = 'CN'").fetchone()[0]
    stocks_with_data = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM daily_prices WHERE market = 'CN'"
    ).fetchone()[0]
    conn.close()
    print(f"DB total CN price records: {count}")
    print(f"DB CN stocks with price data: {stocks_with_data}")


def main():
    parser = argparse.ArgumentParser(description="Batch CN data download")
    parser.add_argument("--step", required=True,
                        choices=["spot", "prefilter", "history", "all"],
                        help="Which step to run")
    parser.add_argument("--max-stocks", type=int, default=None,
                        help="Limit number of stocks for history download")
    args = parser.parse_args()

    if args.step == "spot" or args.step == "all":
        step_spot()
    if args.step == "prefilter" or args.step == "all":
        step_prefilter()
    if args.step == "history" or args.step == "all":
        step_history(max_stocks=args.max_stocks)


if __name__ == "__main__":
    main()
