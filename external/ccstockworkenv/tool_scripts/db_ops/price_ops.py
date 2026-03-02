#!/usr/bin/env python3
"""
Daily price CRUD operations with bulk upsert support.

Usage:
    python price_ops.py --upsert '{"ticker":"AAPL","market":"US","date":"2025-01-01","close":150.0}'
    python price_ops.py --get AAPL --market US --days 30
    python price_ops.py --last-date --market US
    python price_ops.py --bulk-download --market US --days 365
    python price_ops.py --update --market US
"""

import argparse
import json
import sys

from db_manager import get_connection, DB_PATH


def upsert_price(ticker: str, market: str, date: str, open_: float = None,
                 high: float = None, low: float = None, close: float = None,
                 volume: int = None, adj_close: float = None,
                 db_path: str = DB_PATH) -> None:
    """Insert or update a single price record."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO daily_prices (ticker, market, date, open, high, low, close, volume, adj_close)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(ticker, market, date) DO UPDATE SET
               open = COALESCE(excluded.open, daily_prices.open),
               high = COALESCE(excluded.high, daily_prices.high),
               low = COALESCE(excluded.low, daily_prices.low),
               close = COALESCE(excluded.close, daily_prices.close),
               volume = COALESCE(excluded.volume, daily_prices.volume),
               adj_close = COALESCE(excluded.adj_close, daily_prices.adj_close)""",
        (ticker.upper(), market.upper(), date, open_, high, low, close, volume, adj_close),
    )
    conn.commit()
    conn.close()


def bulk_upsert_prices(records: list[dict], db_path: str = DB_PATH) -> int:
    """Bulk upsert price records. Each dict needs: ticker, market, date, and OHLCV fields."""
    conn = get_connection(db_path)
    count = 0
    for r in records:
        conn.execute(
            """INSERT INTO daily_prices (ticker, market, date, open, high, low, close, volume, adj_close)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(ticker, market, date) DO UPDATE SET
                   open = COALESCE(excluded.open, daily_prices.open),
                   high = COALESCE(excluded.high, daily_prices.high),
                   low = COALESCE(excluded.low, daily_prices.low),
                   close = COALESCE(excluded.close, daily_prices.close),
                   volume = COALESCE(excluded.volume, daily_prices.volume),
                   adj_close = COALESCE(excluded.adj_close, daily_prices.adj_close)""",
            (r["ticker"].upper(), r["market"].upper(), r["date"],
             r.get("open"), r.get("high"), r.get("low"), r.get("close"),
             r.get("volume"), r.get("adj_close")),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_prices(ticker: str, market: str, days: int = 30,
               db_path: str = DB_PATH) -> list[dict]:
    """Get recent price history for a stock."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM daily_prices
           WHERE ticker = ? AND market = ?
           ORDER BY date DESC LIMIT ?""",
        (ticker.upper(), market.upper(), days),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_date(market: str = None, db_path: str = DB_PATH) -> str | None:
    """Get the most recent date in the database."""
    conn = get_connection(db_path)
    query = "SELECT MAX(date) FROM daily_prices"
    params = []
    if market:
        query += " WHERE market = ?"
        params.append(market.upper())
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row[0] if row else None


def get_price_range(ticker: str, market: str, start_date: str, end_date: str,
                    db_path: str = DB_PATH) -> list[dict]:
    """Get prices within a date range."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM daily_prices
           WHERE ticker = ? AND market = ? AND date >= ? AND date <= ?
           ORDER BY date""",
        (ticker.upper(), market.upper(), start_date, end_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_stats(ticker: str, market: str, days: int = 252,
                    db_path: str = DB_PATH) -> dict | None:
    """Get price statistics (high, low, avg, etc.) for a period."""
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT
               MIN(low) as period_low,
               MAX(high) as period_high,
               AVG(close) as avg_close,
               MIN(date) as start_date,
               MAX(date) as end_date,
               COUNT(*) as trading_days
           FROM (
               SELECT * FROM daily_prices
               WHERE ticker = ? AND market = ?
               ORDER BY date DESC LIMIT ?
           )""",
        (ticker.upper(), market.upper(), days),
    ).fetchone()
    conn.close()
    return dict(row) if row and row["trading_days"] > 0 else None


def main():
    parser = argparse.ArgumentParser(description="Price data operations")
    parser.add_argument("--upsert", type=str, help="Upsert a price record (JSON)")
    parser.add_argument("--get", type=str, help="Get prices for ticker")
    parser.add_argument("--market", type=str, help="Market code")
    parser.add_argument("--days", type=int, default=30, help="Number of days")
    parser.add_argument("--last-date", action="store_true", help="Get last date in DB")
    parser.add_argument("--stats", type=str, help="Get price stats for ticker")
    parser.add_argument("--bulk-download", action="store_true", help="Bulk download prices")
    parser.add_argument("--update", action="store_true", help="Incremental update")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.upsert:
        data = json.loads(args.upsert)
        upsert_price(**data, db_path=args.db)
        print("Price upserted")

    elif args.get:
        if not args.market:
            print("ERROR: --market is required with --get")
            sys.exit(1)
        prices = get_prices(args.get, args.market, days=args.days, db_path=args.db)
        print(json.dumps(prices, indent=2))
        print(f"\nTotal: {len(prices)} records")

    elif args.last_date:
        date = get_last_date(market=args.market, db_path=args.db)
        print(f"Last date: {date or 'No data'}")

    elif args.stats:
        if not args.market:
            print("ERROR: --market is required with --stats")
            sys.exit(1)
        stats = get_price_stats(args.stats, args.market, days=args.days, db_path=args.db)
        if stats:
            print(json.dumps(stats, indent=2))
        else:
            print("No data found")

    elif args.bulk_download:
        print("Bulk download requires market data fetchers. Use via commands.")
        print("Example: /download_data US --days 365")

    elif args.update:
        print("Incremental update requires market data fetchers. Use via commands.")
        print("Example: /update_db US")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
