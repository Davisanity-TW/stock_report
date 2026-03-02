#!/usr/bin/env python3
"""
Factory for market data fetchers.

Usage as module:
    from fetcher_factory import get_fetcher
    fetcher = get_fetcher("US")
    quote = fetcher.get_quote("AAPL")

Usage as CLI:
    python fetcher_factory.py quote AAPL --market US
    python fetcher_factory.py info 2330 --market TW
    python fetcher_factory.py metrics TSLA --market US
    python fetcher_factory.py financials AAPL --market US --period annual
    python fetcher_factory.py history AAPL --market US --start 2025-01-01 --end 2025-12-31
    python fetcher_factory.py list-tickers --market US
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta

from fetcher_base import MarketDataFetcher
from fetcher_us import USFetcher
from fetcher_tw import TWFetcher
from fetcher_cn import CNFetcher

_FETCHERS = {
    "US": USFetcher,
    "TW": TWFetcher,
    "CN": CNFetcher,
}


def get_fetcher(market: str) -> MarketDataFetcher:
    """Get the appropriate fetcher for a market.

    Args:
        market: Market code (US, TW, CN)

    Returns:
        MarketDataFetcher instance

    Raises:
        ValueError: If market code is not supported
    """
    market = market.upper()
    if market not in _FETCHERS:
        raise ValueError(f"Unsupported market: {market}. Supported: {list(_FETCHERS.keys())}")
    return _FETCHERS[market]()


def detect_market(ticker: str) -> str:
    """Auto-detect market from ticker format.

    Rules:
        - Pure digits, 4 digits → TW
        - Pure digits, 6 digits starting with 6/0/3 → CN
        - Otherwise → US
    """
    clean = ticker.strip()
    if clean.isdigit():
        if len(clean) == 4:
            return "TW"
        if len(clean) == 6 and clean[0] in ("6", "0", "3"):
            return "CN"
        # Could be TW with 5+ digits or other
        return "TW"
    return "US"


def main():
    parser = argparse.ArgumentParser(description="Market data fetcher CLI")
    subparsers = parser.add_subparsers(dest="command")

    # quote
    quote_parser = subparsers.add_parser("quote", help="Get stock quote")
    quote_parser.add_argument("ticker", help="Stock ticker")
    quote_parser.add_argument("--market", help="Market code (US/TW/CN)")

    # info
    info_parser = subparsers.add_parser("info", help="Get company info")
    info_parser.add_argument("ticker", help="Stock ticker")
    info_parser.add_argument("--market", help="Market code")

    # metrics
    metrics_parser = subparsers.add_parser("metrics", help="Get key metrics")
    metrics_parser.add_argument("ticker", help="Stock ticker")
    metrics_parser.add_argument("--market", help="Market code")

    # financials
    fin_parser = subparsers.add_parser("financials", help="Get financials")
    fin_parser.add_argument("ticker", help="Stock ticker")
    fin_parser.add_argument("--market", help="Market code")
    fin_parser.add_argument("--period", default="annual", help="annual or quarterly")

    # history
    hist_parser = subparsers.add_parser("history", help="Get price history")
    hist_parser.add_argument("ticker", help="Stock ticker")
    hist_parser.add_argument("--market", help="Market code")
    hist_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    hist_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    hist_parser.add_argument("--days", type=int, default=365, help="Days of history")

    # list-tickers
    list_parser = subparsers.add_parser("list-tickers", help="List tickers")
    list_parser.add_argument("--market", required=True, help="Market code")
    list_parser.add_argument("--sector", help="Filter by sector")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Detect market if not specified
    market = args.market
    if not market and hasattr(args, "ticker"):
        market = detect_market(args.ticker)
        print(f"Auto-detected market: {market}", file=sys.stderr)

    fetcher = get_fetcher(market)

    if args.command == "quote":
        quote = fetcher.get_quote(args.ticker)
        print(json.dumps(asdict(quote), indent=2, ensure_ascii=False))

    elif args.command == "info":
        info = fetcher.get_company_info(args.ticker)
        print(json.dumps(asdict(info), indent=2, ensure_ascii=False))

    elif args.command == "metrics":
        metrics = fetcher.get_key_metrics(args.ticker)
        print(json.dumps(metrics, indent=2, ensure_ascii=False))

    elif args.command == "financials":
        financials = fetcher.get_financials(args.ticker, period=args.period)
        print(json.dumps(financials, indent=2, ensure_ascii=False))

    elif args.command == "history":
        end = args.end or datetime.now().strftime("%Y-%m-%d")
        start = args.start or (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        history = fetcher.get_price_history(args.ticker, start, end)
        records = [asdict(r) for r in history]
        print(json.dumps(records, indent=2))
        print(f"\n{len(records)} records", file=sys.stderr)

    elif args.command == "list-tickers":
        tickers = fetcher.list_tickers(sector=args.sector)
        print(json.dumps(tickers, indent=2, ensure_ascii=False))
        print(f"\n{len(tickers)} tickers", file=sys.stderr)


if __name__ == "__main__":
    main()
