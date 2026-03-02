#!/usr/bin/env python3
"""
Stock universe CRUD operations.

Usage:
    python stock_ops.py --add AAPL --market US --name "Apple Inc" --sector Technology
    python stock_ops.py --list --market US
    python stock_ops.py --get AAPL --market US
    python stock_ops.py --search "Apple"
    python stock_ops.py --deactivate AAPL --market US
"""

import argparse
import json
import sys

from db_manager import get_connection, DB_PATH


def add_stock(ticker: str, market: str, name: str = None, sector: str = None,
              industry: str = None, currency: str = None, exchange: str = None,
              db_path: str = DB_PATH) -> dict:
    """Add or update a stock in the universe."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO stocks (ticker, market, name, sector, industry, currency, exchange)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(ticker, market) DO UPDATE SET
               name = COALESCE(excluded.name, stocks.name),
               sector = COALESCE(excluded.sector, stocks.sector),
               industry = COALESCE(excluded.industry, stocks.industry),
               currency = COALESCE(excluded.currency, stocks.currency),
               exchange = COALESCE(excluded.exchange, stocks.exchange),
               is_active = 1,
               updated_at = datetime('now')""",
        (ticker.upper(), market.upper(), name, sector, industry, currency, exchange),
    )
    conn.commit()
    conn.close()
    return {"ticker": ticker.upper(), "market": market.upper(), "status": "added"}


def bulk_add_stocks(stocks: list[dict], db_path: str = DB_PATH) -> int:
    """Bulk add stocks. Each dict must have 'ticker' and 'market'."""
    conn = get_connection(db_path)
    count = 0
    for s in stocks:
        conn.execute(
            """INSERT INTO stocks (ticker, market, name, sector, industry, currency, exchange)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(ticker, market) DO UPDATE SET
                   name = COALESCE(excluded.name, stocks.name),
                   sector = COALESCE(excluded.sector, stocks.sector),
                   industry = COALESCE(excluded.industry, stocks.industry),
                   currency = COALESCE(excluded.currency, stocks.currency),
                   exchange = COALESCE(excluded.exchange, stocks.exchange),
                   is_active = 1,
                   updated_at = datetime('now')""",
            (s["ticker"].upper(), s["market"].upper(), s.get("name"),
             s.get("sector"), s.get("industry"), s.get("currency"), s.get("exchange")),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_stock(ticker: str, market: str, db_path: str = DB_PATH) -> dict | None:
    """Get a stock by ticker and market."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM stocks WHERE ticker = ? AND market = ?",
        (ticker.upper(), market.upper()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_stocks(market: str = None, sector: str = None, active_only: bool = True,
                db_path: str = DB_PATH) -> list[dict]:
    """List stocks with optional filters."""
    conn = get_connection(db_path)
    query = "SELECT * FROM stocks WHERE 1=1"
    params = []

    if active_only:
        query += " AND is_active = 1"
    if market:
        query += " AND market = ?"
        params.append(market.upper())
    if sector:
        query += " AND sector = ?"
        params.append(sector)

    query += " ORDER BY market, ticker"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_stocks(query: str, db_path: str = DB_PATH) -> list[dict]:
    """Search stocks by ticker or name."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM stocks
           WHERE (ticker LIKE ? OR name LIKE ?) AND is_active = 1
           ORDER BY market, ticker""",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_stock(ticker: str, market: str, db_path: str = DB_PATH) -> bool:
    """Deactivate a stock (soft delete)."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "UPDATE stocks SET is_active = 0, updated_at = datetime('now') WHERE ticker = ? AND market = ?",
        (ticker.upper(), market.upper()),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def main():
    parser = argparse.ArgumentParser(description="Stock universe operations")
    parser.add_argument("--add", type=str, help="Add stock ticker")
    parser.add_argument("--market", type=str, help="Market code (US/TW/CN)")
    parser.add_argument("--name", type=str, help="Company name")
    parser.add_argument("--sector", type=str, help="Sector")
    parser.add_argument("--list", action="store_true", help="List stocks")
    parser.add_argument("--get", type=str, help="Get stock by ticker")
    parser.add_argument("--search", type=str, help="Search stocks")
    parser.add_argument("--deactivate", type=str, help="Deactivate stock")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.add:
        if not args.market:
            print("ERROR: --market is required with --add")
            sys.exit(1)
        result = add_stock(args.add, args.market, name=args.name, sector=args.sector, db_path=args.db)
        print(json.dumps(result, indent=2))

    elif args.list:
        stocks = list_stocks(market=args.market, sector=args.sector, db_path=args.db)
        print(json.dumps(stocks, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(stocks)} stocks")

    elif args.get:
        if not args.market:
            print("ERROR: --market is required with --get")
            sys.exit(1)
        stock = get_stock(args.get, args.market, db_path=args.db)
        if stock:
            print(json.dumps(stock, indent=2, ensure_ascii=False))
        else:
            print(f"Stock not found: {args.get} ({args.market})")

    elif args.search:
        results = search_stocks(args.search, db_path=args.db)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nFound: {len(results)} stocks")

    elif args.deactivate:
        if not args.market:
            print("ERROR: --market is required with --deactivate")
            sys.exit(1)
        success = deactivate_stock(args.deactivate, args.market, db_path=args.db)
        print("Deactivated" if success else "Stock not found")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
