#!/usr/bin/env python3
"""
Financial statement CRUD operations + health scores compute & storage.

Usage:
    python financial_ops.py --get AAPL --market US --period annual
    python financial_ops.py --list --market US --period quarterly
    python financial_ops.py --bulk-upsert --json '<json_array>'
    python financial_ops.py --compute-health AAPL --market US
    python financial_ops.py --get-health AAPL --market US
"""

import argparse
import json
import sys

from db_manager import get_connection, DB_PATH


def _normalize_ticker(ticker: str) -> str:
    """Strip exchange suffixes (.SS, .SZ, .TW, .TWO) for consistent DB keys."""
    for suffix in (".SS", ".SZ", ".TW", ".TWO"):
        if ticker.upper().endswith(suffix):
            return ticker[: -len(suffix)].upper()
    return ticker.upper()


def _ensure_stock_exists(conn, ticker: str, market: str) -> None:
    """Auto-create stock entry if it doesn't exist (satisfies FK constraint)."""
    conn.execute(
        "INSERT OR IGNORE INTO stocks (ticker, market) VALUES (?, ?)",
        (ticker.upper(), market.upper()),
    )


def upsert_financials(data: dict, db_path: str = DB_PATH) -> None:
    """Insert or update financial data. data must contain ticker, market, period, period_date."""
    data["ticker"] = _normalize_ticker(data["ticker"])
    conn = get_connection(db_path)
    _ensure_stock_exists(conn, data["ticker"], data["market"])

    fields = [
        "ticker", "market", "period", "period_date",
        "revenue", "gross_profit", "operating_income", "ebit", "net_income", "eps",
        "total_assets", "total_liabilities", "total_equity",
        "current_assets", "current_liabilities", "long_term_debt",
        "retained_earnings", "working_capital",
        "operating_cash_flow", "capex", "fcf",
        "market_cap", "shares_outstanding",
        "pe_ratio", "pb_ratio", "roe", "roa", "de_ratio", "current_ratio",
        "gross_margin", "operating_margin", "net_margin",
        "asset_turnover", "dividend_yield", "fcf_yield",
        # v2 columns
        "quick_ratio", "interest_coverage", "ps_ratio", "ev_ebitda",
        "payout_ratio", "cash_and_equivalents", "total_debt", "ebitda",
        "inventory", "receivables", "inventory_turnover_days", "receivable_turnover_days",
    ]

    values = [data.get(f) for f in fields]

    placeholders = ", ".join(["?"] * len(fields))
    field_names = ", ".join(fields)

    update_fields = [f for f in fields if f not in ("ticker", "market", "period", "period_date")]
    update_clause = ", ".join(
        f"{f} = COALESCE(excluded.{f}, financials.{f})" for f in update_fields
    )
    update_clause += ", updated_at = datetime('now')"

    conn.execute(
        f"""INSERT INTO financials ({field_names})
            VALUES ({placeholders})
            ON CONFLICT(ticker, market, period, period_date) DO UPDATE SET
                {update_clause}""",
        values,
    )
    conn.commit()
    conn.close()


def bulk_upsert_financials(records: list[dict], db_path: str = DB_PATH) -> int:
    """Bulk upsert financial records."""
    count = 0
    for r in records:
        upsert_financials(r, db_path)
        count += 1
    return count


def get_financials(ticker: str, market: str, period: str = "annual",
                   limit: int = 8, db_path: str = DB_PATH) -> list[dict]:
    """Get financial records for a stock."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM financials
           WHERE ticker = ? AND market = ? AND period = ?
           ORDER BY period_date DESC LIMIT ?""",
        (_normalize_ticker(ticker), market.upper(), period, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_financials(ticker: str, market: str,
                          db_path: str = DB_PATH) -> dict | None:
    """Get the most recent financial record for a stock."""
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT * FROM financials
           WHERE ticker = ? AND market = ?
           ORDER BY period_date DESC LIMIT 1""",
        (_normalize_ticker(ticker), market.upper()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_financials_summary(market: str = None, period: str = "annual",
                            db_path: str = DB_PATH) -> list[dict]:
    """List available financial data summary."""
    conn = get_connection(db_path)
    query = """SELECT ticker, market, period, COUNT(*) as periods_count,
                      MIN(period_date) as earliest, MAX(period_date) as latest
               FROM financials WHERE period = ?"""
    params = [period]
    if market:
        query += " AND market = ?"
        params.append(market.upper())
    query += " GROUP BY ticker, market, period ORDER BY market, ticker"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_health_scores(data: dict, db_path: str = DB_PATH) -> None:
    """Insert or update a health_scores record. PK: (ticker, market, period, period_date)."""
    data["ticker"] = _normalize_ticker(data["ticker"])
    conn = get_connection(db_path)
    fields = [
        "ticker", "market", "period", "period_date",
        "zscore", "zscore_zone", "quick_ratio", "interest_coverage",
        "fscore", "fscore_details_json",
        "ocf_to_net_income",
        "revenue_growth", "net_income_growth", "eps_growth",
        "opportunity_score", "opportunity_details_json",
    ]
    values = [data.get(f) for f in fields]
    placeholders = ", ".join(["?"] * len(fields))
    field_names = ", ".join(fields)

    update_fields = [f for f in fields if f not in ("ticker", "market", "period", "period_date")]
    update_clause = ", ".join(
        f"{f} = COALESCE(excluded.{f}, health_scores.{f})" for f in update_fields
    )

    conn.execute(
        f"""INSERT INTO health_scores ({field_names})
            VALUES ({placeholders})
            ON CONFLICT(ticker, market, period, period_date) DO UPDATE SET
                {update_clause}""",
        values,
    )
    conn.commit()
    conn.close()


def get_health_scores(ticker: str, market: str, period: str = "annual",
                      limit: int = 8, db_path: str = DB_PATH) -> list[dict]:
    """Get health scores for a stock."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM health_scores
           WHERE ticker = ? AND market = ? AND period = ?
           ORDER BY period_date DESC LIMIT ?""",
        (_normalize_ticker(ticker), market.upper(), period, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _safe_div(a, b):
    """Safe division returning None if inputs are invalid."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct_growth(current, prior):
    """Calculate percentage growth. Returns None if inputs are invalid."""
    if current is None or prior is None or prior == 0:
        return None
    return round((current - prior) / abs(prior) * 100, 2)


def compute_and_save_health(ticker: str, market: str, period: str = "annual",
                            db_path: str = DB_PATH) -> list[dict]:
    """Read financials from DB, compute health scores, save to health_scores table.

    Computes: Z-Score, F-Score, growth rates, cash flow quality for each period.
    Returns the computed health scores.
    """
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "financial_calc"))
    from zscore import calculate_zscore
    from fscore import calculate_fscore

    records = get_financials(ticker, market, period=period, limit=10, db_path=db_path)
    if not records:
        print(f"No financials in DB for {ticker} ({market})")
        return []

    results = []
    for i, current in enumerate(records):
        prior = records[i + 1] if i + 1 < len(records) else None

        health = {
            "ticker": current["ticker"],
            "market": current["market"],
            "period": current["period"],
            "period_date": current["period_date"],
        }

        # Z-Score
        zscore_result = calculate_zscore(current)
        health["zscore"] = zscore_result["zscore"]
        health["zscore_zone"] = zscore_result["zone"]

        # F-Score (needs prior period)
        if prior:
            fscore_result = calculate_fscore(current, prior)
            health["fscore"] = fscore_result["fscore"]
            health["fscore_details_json"] = json.dumps(fscore_result["details"])
        else:
            health["fscore"] = None
            health["fscore_details_json"] = None

        # Solvency ratios from financials
        health["quick_ratio"] = current.get("quick_ratio")
        health["interest_coverage"] = current.get("interest_coverage")

        # Cash flow quality
        health["ocf_to_net_income"] = _safe_div(
            current.get("operating_cash_flow"), current.get("net_income")
        )
        if health["ocf_to_net_income"] is not None:
            health["ocf_to_net_income"] = round(health["ocf_to_net_income"], 4)

        # Growth (YoY)
        if prior:
            health["revenue_growth"] = _pct_growth(current.get("revenue"), prior.get("revenue"))
            health["net_income_growth"] = _pct_growth(current.get("net_income"), prior.get("net_income"))
            health["eps_growth"] = _pct_growth(current.get("eps"), prior.get("eps"))
        else:
            health["revenue_growth"] = None
            health["net_income_growth"] = None
            health["eps_growth"] = None

        upsert_health_scores(health, db_path)
        results.append(health)

    return results


def main():
    parser = argparse.ArgumentParser(description="Financial data operations")
    parser.add_argument("--get", type=str, help="Get financials for ticker")
    parser.add_argument("--market", type=str, help="Market code")
    parser.add_argument("--period", type=str, default="annual", help="annual or quarterly")
    parser.add_argument("--list", action="store_true", help="List available financials")
    parser.add_argument("--limit", type=int, default=8, help="Max periods to return")
    parser.add_argument("--bulk-upsert", action="store_true", help="Bulk upsert from JSON")
    parser.add_argument("--json", type=str, help="JSON array for bulk upsert (or '-' for stdin)")
    parser.add_argument("--compute-health", type=str, help="Compute health scores for ticker")
    parser.add_argument("--get-health", type=str, help="Get health scores for ticker")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.get:
        if not args.market:
            print("ERROR: --market is required with --get")
            sys.exit(1)
        records = get_financials(args.get, args.market, period=args.period,
                                 limit=args.limit, db_path=args.db)
        print(json.dumps(records, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(records)} periods")

    elif args.bulk_upsert:
        if not args.json:
            print("ERROR: --json is required with --bulk-upsert")
            sys.exit(1)
        if args.json == "-":
            data = json.load(sys.stdin)
        else:
            data = json.loads(args.json)
        if isinstance(data, dict):
            data = [data]
        count = bulk_upsert_financials(data, args.db)
        print(json.dumps({"status": "ok", "upserted": count}))

    elif args.compute_health:
        if not args.market:
            print("ERROR: --market is required with --compute-health")
            sys.exit(1)
        results = compute_and_save_health(args.compute_health, args.market,
                                          period=args.period, db_path=args.db)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nComputed health scores for {len(results)} periods")

    elif args.get_health:
        if not args.market:
            print("ERROR: --market is required with --get-health")
            sys.exit(1)
        records = get_health_scores(args.get_health, args.market,
                                    period=args.period, limit=args.limit, db_path=args.db)
        print(json.dumps(records, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(records)} health score records")

    elif args.list:
        summary = list_financials_summary(market=args.market, period=args.period, db_path=args.db)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(summary)} stocks with financial data")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
