#!/usr/bin/env python3
"""
Watchlist & notes CRUD operations.

Usage:
    python watchlist_ops.py --add AAPL --market US --notes "Watch for earnings"
    python watchlist_ops.py --list
    python watchlist_ops.py --remove AAPL --market US
"""

import argparse
import json
import sys

from db_manager import get_connection, DB_PATH


def add_to_watchlist(ticker: str, market: str, target_price: float = None,
                     stop_loss: float = None, notes: str = None, tags: str = None,
                     db_path: str = DB_PATH) -> dict:
    """Add a stock to the watchlist."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO watchlist (ticker, market, target_price, stop_loss, notes, tags)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(ticker, market) DO UPDATE SET
               target_price = COALESCE(excluded.target_price, watchlist.target_price),
               stop_loss = COALESCE(excluded.stop_loss, watchlist.stop_loss),
               notes = COALESCE(excluded.notes, watchlist.notes),
               tags = COALESCE(excluded.tags, watchlist.tags),
               is_active = 1""",
        (ticker.upper(), market.upper(), target_price, stop_loss, notes, tags),
    )
    conn.commit()
    conn.close()
    return {"ticker": ticker.upper(), "market": market.upper(), "status": "added"}


def list_watchlist(market: str = None, tag: str = None, active_only: bool = True,
                   db_path: str = DB_PATH) -> list[dict]:
    """List watchlist items."""
    conn = get_connection(db_path)
    query = "SELECT * FROM watchlist WHERE 1=1"
    params = []

    if active_only:
        query += " AND is_active = 1"
    if market:
        query += " AND market = ?"
        params.append(market.upper())
    if tag:
        query += " AND tags LIKE ?"
        params.append(f"%{tag}%")

    query += " ORDER BY added_date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_watchlist_item(ticker: str, market: str, db_path: str = DB_PATH) -> dict | None:
    """Get a watchlist item."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM watchlist WHERE ticker = ? AND market = ?",
        (ticker.upper(), market.upper()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_watchlist(ticker: str, market: str, target_price: float = None,
                     stop_loss: float = None, notes: str = None, tags: str = None,
                     db_path: str = DB_PATH) -> bool:
    """Update a watchlist item."""
    conn = get_connection(db_path)
    updates = []
    params = []

    if target_price is not None:
        updates.append("target_price = ?")
        params.append(target_price)
    if stop_loss is not None:
        updates.append("stop_loss = ?")
        params.append(stop_loss)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if tags is not None:
        updates.append("tags = ?")
        params.append(tags)

    if not updates:
        return False

    params.extend([ticker.upper(), market.upper()])
    cursor = conn.execute(
        f"UPDATE watchlist SET {', '.join(updates)} WHERE ticker = ? AND market = ?",
        params,
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def remove_from_watchlist(ticker: str, market: str, db_path: str = DB_PATH) -> bool:
    """Remove a stock from the watchlist (soft delete)."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "UPDATE watchlist SET is_active = 0 WHERE ticker = ? AND market = ?",
        (ticker.upper(), market.upper()),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def main():
    parser = argparse.ArgumentParser(description="Watchlist operations")
    parser.add_argument("--add", type=str, help="Add ticker to watchlist")
    parser.add_argument("--market", type=str, help="Market code")
    parser.add_argument("--target", type=float, help="Target price")
    parser.add_argument("--stop", type=float, help="Stop loss price")
    parser.add_argument("--notes", type=str, help="Notes")
    parser.add_argument("--tags", type=str, help="Comma-separated tags")
    parser.add_argument("--list", action="store_true", help="List watchlist")
    parser.add_argument("--remove", type=str, help="Remove from watchlist")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.add:
        if not args.market:
            print("ERROR: --market is required with --add")
            sys.exit(1)
        result = add_to_watchlist(args.add, args.market, target_price=args.target,
                                  stop_loss=args.stop, notes=args.notes, tags=args.tags,
                                  db_path=args.db)
        print(json.dumps(result, indent=2))

    elif args.list:
        items = list_watchlist(market=args.market, db_path=args.db)
        print(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(items)} items")

    elif args.remove:
        if not args.market:
            print("ERROR: --market is required with --remove")
            sys.exit(1)
        success = remove_from_watchlist(args.remove, args.market, db_path=args.db)
        print("Removed" if success else "Not found")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
