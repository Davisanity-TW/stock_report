#!/usr/bin/env python3
"""
Altman Z-Score calculator.

The Z-Score predicts the probability of a company going bankrupt.

Formula (manufacturing):
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

Where:
    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT / Total Assets
    X4 = Market Cap / Total Liabilities
    X5 = Revenue / Total Assets

Zones:
    Z > 2.99  → Safe Zone (low bankruptcy risk)
    1.81-2.99 → Grey Zone (moderate risk)
    Z < 1.81  → Distress Zone (high bankruptcy risk)

Usage:
    python zscore.py AAPL --market US
    python zscore.py 2330 --market TW
"""

import argparse
import json
import sys
import os


def calculate_zscore(financials: dict) -> dict:
    """Calculate Altman Z-Score from financial data.

    Args:
        financials: dict with keys: working_capital, retained_earnings, ebit,
                    market_cap, total_liabilities, revenue, total_assets

    Returns:
        dict with zscore, zone, and component breakdown
    """
    ta = financials["total_assets"]
    if not ta or ta == 0:
        return {"zscore": None, "zone": "insufficient_data", "components": {}}

    wc = financials.get("working_capital", 0) or 0
    re = financials.get("retained_earnings", 0) or 0
    ebit = financials.get("ebit", 0) or 0
    mc = financials.get("market_cap", 0) or 0
    tl = financials.get("total_liabilities", 0) or 0
    rev = financials.get("revenue", 0) or 0

    x1 = wc / ta
    x2 = re / ta
    x3 = ebit / ta
    x4 = mc / tl if tl != 0 else 0
    x5 = rev / ta

    zscore = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    if zscore > 2.99:
        zone = "safe"
    elif zscore >= 1.81:
        zone = "grey"
    else:
        zone = "distress"

    return {
        "zscore": round(zscore, 4),
        "zone": zone,
        "components": {
            "X1_working_capital_ratio": round(x1, 4),
            "X2_retained_earnings_ratio": round(x2, 4),
            "X3_ebit_ratio": round(x3, 4),
            "X4_market_equity_ratio": round(x4, 4),
            "X5_asset_turnover": round(x5, 4),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate Altman Z-Score")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("--market", help="Market code (US/TW/CN)")

    args = parser.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
    from fetcher_factory import get_fetcher, detect_market

    market = args.market or detect_market(args.ticker)
    fetcher = get_fetcher(market)

    # Get latest financials
    financials_list = fetcher.get_financials(args.ticker, period="annual")
    if not financials_list:
        print(f"No financial data available for {args.ticker}")
        sys.exit(1)

    latest = financials_list[0]

    # Get market cap from key metrics
    metrics = fetcher.get_key_metrics(args.ticker)
    latest["market_cap"] = metrics.get("market_cap", 0)

    result = calculate_zscore(latest)
    result["ticker"] = args.ticker.upper()
    result["market"] = market
    result["period_date"] = latest.get("period_date", "unknown")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
