#!/usr/bin/env python3
"""
Research cache CRUD operations.

Tracks when financial data was last fetched from APIs to avoid redundant calls.

Freshness policy:
    financials  → 90 days  (quarterly filing cycle)
    metrics     → 24 hours (price-dependent ratios)
    company_info → 180 days (rarely changes)

Usage:
    python research_cache_ops.py --is-fresh AAPL US financials
    python research_cache_ops.py --mark AAPL US financials
    python research_cache_ops.py --mark AAPL US metrics --data '{"pe_ratio": 28.5}'
    python research_cache_ops.py --get AAPL US metrics
    python research_cache_ops.py --summary
    python research_cache_ops.py --clear AAPL US financials
    python research_cache_ops.py --clear-all
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

from db_manager import get_connection, DB_PATH

FRESHNESS_DAYS = {
    "financials": 90,
    "metrics": 1,
    "company_info": 180,
}


def _normalize_ticker(ticker: str) -> str:
    """Strip exchange suffixes (.SS, .SZ, .TW, .TWO) for consistent DB keys."""
    for suffix in (".SS", ".SZ", ".TW", ".TWO"):
        if ticker.upper().endswith(suffix):
            return ticker[: -len(suffix)].upper()
    return ticker.upper()


def upsert_cache(ticker: str, market: str, data_type: str,
                 data_json: str = None, fetch_source: str = None,
                 db_path: str = DB_PATH) -> None:
    """Insert or update a cache entry with current timestamp."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO research_cache (ticker, market, data_type, last_fetched_at, data_json, fetch_source)
           VALUES (?, ?, ?, datetime('now'), ?, ?)
           ON CONFLICT(ticker, market, data_type) DO UPDATE SET
               last_fetched_at = datetime('now'),
               data_json = COALESCE(excluded.data_json, research_cache.data_json),
               fetch_source = COALESCE(excluded.fetch_source, research_cache.fetch_source)""",
        (_normalize_ticker(ticker), market.upper(), data_type, data_json, fetch_source),
    )
    conn.commit()
    conn.close()


def get_cache(ticker: str, market: str, data_type: str,
              db_path: str = DB_PATH) -> dict | None:
    """Get a cache entry."""
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT * FROM research_cache
           WHERE ticker = ? AND market = ? AND data_type = ?""",
        (_normalize_ticker(ticker), market.upper(), data_type),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def is_cache_fresh(ticker: str, market: str, data_type: str,
                   db_path: str = DB_PATH) -> dict:
    """Check if cached data is still fresh.

    Returns:
        dict with keys: fresh (bool), last_fetched_at (str|None), age_days (float|None),
                        max_age_days (int), has_data (bool)
    """
    max_age = FRESHNESS_DAYS.get(data_type, 90)
    entry = get_cache(ticker, market, data_type, db_path)

    if not entry:
        return {
            "fresh": False,
            "last_fetched_at": None,
            "age_days": None,
            "max_age_days": max_age,
            "has_data": False,
        }

    fetched_at = datetime.fromisoformat(entry["last_fetched_at"])
    age = datetime.now(tz=None) - fetched_at
    age_days = round(age.total_seconds() / 86400, 1)
    fresh = age < timedelta(days=max_age)

    return {
        "fresh": fresh,
        "last_fetched_at": entry["last_fetched_at"],
        "age_days": age_days,
        "max_age_days": max_age,
        "has_data": entry["data_json"] is not None,
    }


def clear_cache(ticker: str, market: str, data_type: str,
                db_path: str = DB_PATH) -> bool:
    """Delete a specific cache entry. Returns True if deleted."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "DELETE FROM research_cache WHERE ticker = ? AND market = ? AND data_type = ?",
        (_normalize_ticker(ticker), market.upper(), data_type),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def clear_all_cache(db_path: str = DB_PATH) -> int:
    """Delete all cache entries. Returns count deleted."""
    conn = get_connection(db_path)
    cursor = conn.execute("DELETE FROM research_cache")
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


def get_cache_summary(db_path: str = DB_PATH) -> list[dict]:
    """Get a summary of all cache entries with freshness status."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT ticker, market, data_type, last_fetched_at, fetch_source,
                  LENGTH(data_json) as data_size
           FROM research_cache ORDER BY market, ticker, data_type"""
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        fetched_at = datetime.fromisoformat(r["last_fetched_at"])
        age = datetime.now(tz=None) - fetched_at
        age_days = round(age.total_seconds() / 86400, 1)
        max_age = FRESHNESS_DAYS.get(r["data_type"], 90)
        r["age_days"] = age_days
        r["max_age_days"] = max_age
        r["fresh"] = age < timedelta(days=max_age)
        results.append(r)

    return results


def main():
    parser = argparse.ArgumentParser(description="Research cache operations")
    parser.add_argument("--is-fresh", nargs=3, metavar=("TICKER", "MARKET", "TYPE"),
                        help="Check if cache is fresh")
    parser.add_argument("--mark", nargs=3, metavar=("TICKER", "MARKET", "TYPE"),
                        help="Mark data as freshly fetched")
    parser.add_argument("--get", nargs=3, metavar=("TICKER", "MARKET", "TYPE"),
                        help="Get cached data")
    parser.add_argument("--summary", action="store_true",
                        help="Show all cache entries with freshness")
    parser.add_argument("--clear", nargs=3, metavar=("TICKER", "MARKET", "TYPE"),
                        help="Clear a specific cache entry")
    parser.add_argument("--clear-all", action="store_true",
                        help="Clear all cache entries")
    parser.add_argument("--data", type=str, help="JSON data to store (with --mark)")
    parser.add_argument("--source", type=str, help="Fetch source name (with --mark)")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.is_fresh:
        ticker, market, data_type = args.is_fresh
        result = is_cache_fresh(ticker, market, data_type, args.db)
        print(json.dumps(result, indent=2))

    elif args.mark:
        ticker, market, data_type = args.mark
        upsert_cache(ticker, market, data_type,
                     data_json=args.data, fetch_source=args.source,
                     db_path=args.db)
        print(json.dumps({"status": "ok", "ticker": ticker.upper(),
                          "market": market.upper(), "data_type": data_type}))

    elif args.get:
        ticker, market, data_type = args.get
        entry = get_cache(ticker, market, data_type, args.db)
        if entry:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"status": "not_found"}))

    elif args.summary:
        entries = get_cache_summary(args.db)
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(entries)} cache entries")

    elif args.clear:
        ticker, market, data_type = args.clear
        deleted = clear_cache(ticker, market, data_type, args.db)
        print(json.dumps({"deleted": deleted, "ticker": ticker.upper(),
                          "market": market.upper(), "data_type": data_type}))

    elif args.clear_all:
        count = clear_all_cache(args.db)
        print(json.dumps({"deleted_count": count}))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
