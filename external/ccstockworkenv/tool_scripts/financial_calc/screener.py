#!/usr/bin/env python3
"""
Stock screening engine.

Screens stocks based on financial criteria.

Usage:
    python screener.py --market US --criteria '{"filters": [{"metric": "pe_ratio", "op": "<", "value": 15}]}'
    python screener.py --market TW --criteria '{"filters": [{"metric": "roe", "op": ">", "value": 0.15}]}'
"""

import argparse
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "db_ops"))

from fetcher_factory import get_fetcher


OPERATORS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def screen_stocks(market: str, filters: list[dict], max_results: int = 50,
                  use_db: bool = True) -> list[dict]:
    """Screen stocks based on criteria.

    Args:
        market: Market code (US/TW/CN)
        filters: List of filter dicts with 'metric', 'op', 'value' keys
        max_results: Maximum number of results to return
        use_db: If True, try to use cached DB data first

    Returns:
        List of matching stocks with their metrics
    """
    fetcher = get_fetcher(market)

    # Try to get ticker list
    tickers = fetcher.list_tickers()
    if not tickers:
        print(f"No tickers available for market: {market}", file=sys.stderr)
        return []

    results = []
    errors = 0

    for i, stock_info in enumerate(tickers):
        ticker = stock_info["ticker"]

        try:
            metrics = fetcher.get_key_metrics(ticker)

            # Apply all filters
            passes = True
            for f in filters:
                metric_val = metrics.get(f["metric"])
                if metric_val is None:
                    passes = False
                    break

                op_func = OPERATORS[f["op"]]
                if not op_func(metric_val, f["value"]):
                    passes = False
                    break

            if passes:
                results.append({
                    "ticker": ticker,
                    "name": stock_info.get("name", ticker),
                    "market": market,
                    **{f["metric"]: metrics.get(f["metric"]) for f in filters},
                    "market_cap": metrics.get("market_cap"),
                })

                if len(results) >= max_results:
                    break

        except Exception as e:
            errors += 1
            print(f"Error fetching {ticker}: {e}", file=sys.stderr)

        # Rate limiting
        if i > 0 and i % 10 == 0:
            time.sleep(0.5)

    return results


def screen_from_db(market: str, filters: list[dict], max_results: int = 50) -> list[dict]:
    """Screen stocks using cached data in SQLite database.

    This is much faster than live API calls as it uses pre-downloaded data.
    """
    try:
        from db_manager import get_connection, DB_PATH
    except ImportError:
        print("Database not available, falling back to live API", file=sys.stderr)
        return screen_stocks(market, filters, max_results, use_db=False)

    conn = get_connection()

    # Build WHERE clauses from filters
    where_parts = ["f.market = ?"]
    params = [market.upper()]

    # Map metric names to SQL columns
    metric_to_column = {
        "pe_ratio": "f.pe_ratio",
        "pb_ratio": "f.pb_ratio",
        "roe": "f.roe",
        "roa": "f.roa",
        "de_ratio": "f.de_ratio",
        "current_ratio": "f.current_ratio",
        "gross_margin": "f.gross_margin",
        "operating_margin": "f.operating_margin",
        "net_margin": "f.net_margin",
        "dividend_yield": "f.dividend_yield",
        "market_cap": "f.market_cap",
        "revenue": "f.revenue",
        "net_income": "f.net_income",
        "fcf": "f.fcf",
    }

    for f in filters:
        col = metric_to_column.get(f["metric"])
        if col is None:
            print(f"Warning: metric '{f['metric']}' not available in DB screening", file=sys.stderr)
            continue
        where_parts.append(f"{col} IS NOT NULL AND {col} {f['op']} ?")
        params.append(f["value"])

    where_clause = " AND ".join(where_parts)

    query = f"""
        SELECT s.ticker, s.market, s.name, f.*
        FROM financials f
        JOIN stocks s ON f.ticker = s.ticker AND f.market = s.market
        WHERE {where_clause}
            AND f.period_date = (
                SELECT MAX(period_date) FROM financials
                WHERE ticker = f.ticker AND market = f.market AND period = 'annual'
            )
            AND s.is_active = 1
        ORDER BY f.pe_ratio
        LIMIT ?
    """
    params.append(max_results)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Screen stocks")
    parser.add_argument("--market", required=True, help="Market code (US/TW/CN)")
    parser.add_argument("--criteria", required=True, help="JSON criteria string")
    parser.add_argument("--max", type=int, default=50, help="Max results")
    parser.add_argument("--live", action="store_true", help="Use live API instead of DB")

    args = parser.parse_args()
    criteria = json.loads(args.criteria)
    filters = criteria["filters"]

    if args.live:
        results = screen_stocks(args.market, filters, max_results=args.max)
    else:
        results = screen_from_db(args.market, filters, max_results=args.max)

    output = {
        "market": args.market.upper(),
        "criteria": criteria,
        "count": len(results),
        "results": results,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
