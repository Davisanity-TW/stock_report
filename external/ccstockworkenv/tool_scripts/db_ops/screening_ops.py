#!/usr/bin/env python3
"""
Screening results CRUD operations.

Usage:
    python screening_ops.py --list
    python screening_ops.py --get 1
    python screening_ops.py --save --market US --criteria '{"filters":[]}' --results '[{"ticker":"AAPL"}]'
"""

import argparse
import json
import sys

from db_manager import get_connection, DB_PATH


def save_screening(market: str, criteria_json: str, results_json: str,
                   notes: str = None, db_path: str = DB_PATH) -> int:
    """Save a screening result. Returns the new record ID."""
    conn = get_connection(db_path)
    results = json.loads(results_json)
    cursor = conn.execute(
        """INSERT INTO screening_results (market, criteria_json, result_count, results_json, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (market.upper() if market else None, criteria_json, len(results), results_json, notes),
    )
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id


def get_screening(screening_id: int, db_path: str = DB_PATH) -> dict | None:
    """Get a screening result by ID."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM screening_results WHERE id = ?", (screening_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_screenings(limit: int = 20, db_path: str = DB_PATH) -> list[dict]:
    """List recent screening results."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT id, run_date, market, criteria_json, result_count, notes
           FROM screening_results ORDER BY run_date DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_screening(screening_id: int, db_path: str = DB_PATH) -> bool:
    """Delete a screening result."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "DELETE FROM screening_results WHERE id = ?", (screening_id,)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def main():
    parser = argparse.ArgumentParser(description="Screening results operations")
    parser.add_argument("--save", action="store_true", help="Save screening result")
    parser.add_argument("--market", type=str, help="Market code")
    parser.add_argument("--criteria", type=str, help="Criteria JSON")
    parser.add_argument("--results", type=str, help="Results JSON array")
    parser.add_argument("--notes", type=str, help="Notes")
    parser.add_argument("--get", type=int, help="Get screening by ID")
    parser.add_argument("--list", action="store_true", help="List screenings")
    parser.add_argument("--delete", type=int, help="Delete screening by ID")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.save:
        if not args.criteria or not args.results:
            print("ERROR: --criteria and --results are required with --save")
            sys.exit(1)
        record_id = save_screening(args.market, args.criteria, args.results,
                                   notes=args.notes, db_path=args.db)
        print(f"Saved screening result with ID: {record_id}")

    elif args.get is not None:
        result = get_screening(args.get, db_path=args.db)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Screening not found: {args.get}")

    elif args.list:
        results = list_screenings(limit=args.limit, db_path=args.db)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(results)} screenings")

    elif args.delete is not None:
        success = delete_screening(args.delete, db_path=args.db)
        print("Deleted" if success else "Not found")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
