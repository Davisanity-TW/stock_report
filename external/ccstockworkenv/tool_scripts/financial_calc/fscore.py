#!/usr/bin/env python3
"""
Piotroski F-Score calculator.

The F-Score assesses the financial strength of a company (0-9 scale).
Score ≥ 7: Strong | 4-6: Average | ≤ 3: Weak

Nine criteria across three categories:

Profitability (4 points):
1. ROA > 0 (positive net income)
2. Operating Cash Flow > 0
3. ROA increasing (vs prior year)
4. Cash Flow from Operations > Net Income (quality of earnings)

Leverage/Liquidity (3 points):
5. Long-term debt ratio decreasing
6. Current ratio increasing
7. No new shares issued

Operating Efficiency (2 points):
8. Gross margin increasing
9. Asset turnover ratio increasing

Usage:
    python fscore.py AAPL --market US
    python fscore.py 2330 --market TW
"""

import argparse
import json
import sys
import os


def calculate_fscore(current: dict, prior: dict) -> dict:
    """Calculate Piotroski F-Score from current and prior year financials.

    Args:
        current: dict with financial data for current period
        prior: dict with financial data for prior period

    Returns:
        dict with fscore (0-9), category scores, and details
    """
    details = {}
    score = 0

    # Helper
    def _safe_div(a, b):
        if a is None or b is None or b == 0:
            return None
        return a / b

    # Current period values
    ta_curr = current.get("total_assets") or 0
    ta_prior = prior.get("total_assets") or 0

    ni_curr = current.get("net_income")
    ocf_curr = current.get("operating_cash_flow")
    ni_prior = prior.get("net_income")

    roa_curr = _safe_div(ni_curr, ta_curr) if ta_curr else None
    roa_prior = _safe_div(ni_prior, ta_prior) if ta_prior else None

    # === Profitability (4 points) ===

    # 1. ROA > 0
    p1 = 1 if roa_curr is not None and roa_curr > 0 else 0
    details["roa_positive"] = p1

    # 2. Operating Cash Flow > 0
    p2 = 1 if ocf_curr is not None and ocf_curr > 0 else 0
    details["ocf_positive"] = p2

    # 3. ROA increasing
    p3 = 0
    if roa_curr is not None and roa_prior is not None:
        p3 = 1 if roa_curr > roa_prior else 0
    details["roa_increasing"] = p3

    # 4. Cash flow > Net income (accruals)
    p4 = 0
    if ocf_curr is not None and ni_curr is not None:
        p4 = 1 if ocf_curr > ni_curr else 0
    details["ocf_gt_net_income"] = p4

    profitability = p1 + p2 + p3 + p4

    # === Leverage/Liquidity (3 points) ===

    # 5. Long-term debt ratio decreasing
    ltd_curr = _safe_div(current.get("long_term_debt"), ta_curr)
    ltd_prior = _safe_div(prior.get("long_term_debt"), ta_prior)
    p5 = 0
    if ltd_curr is not None and ltd_prior is not None:
        p5 = 1 if ltd_curr < ltd_prior else 0
    elif ltd_curr is not None and ltd_curr == 0:
        p5 = 1  # No debt is good
    details["ltd_decreasing"] = p5

    # 6. Current ratio increasing
    cr_curr = _safe_div(current.get("current_assets"), current.get("current_liabilities"))
    cr_prior = _safe_div(prior.get("current_assets"), prior.get("current_liabilities"))
    p6 = 0
    if cr_curr is not None and cr_prior is not None:
        p6 = 1 if cr_curr > cr_prior else 0
    details["current_ratio_increasing"] = p6

    # 7. No new shares issued
    shares_curr = current.get("shares_outstanding")
    shares_prior = prior.get("shares_outstanding")
    p7 = 0
    if shares_curr is not None and shares_prior is not None:
        p7 = 1 if shares_curr <= shares_prior else 0
    else:
        p7 = 1  # Assume no dilution if data unavailable
    details["no_dilution"] = p7

    leverage = p5 + p6 + p7

    # === Operating Efficiency (2 points) ===

    # 8. Gross margin increasing
    gm_curr = _safe_div(current.get("gross_profit"), current.get("revenue"))
    gm_prior = _safe_div(prior.get("gross_profit"), prior.get("revenue"))
    p8 = 0
    if gm_curr is not None and gm_prior is not None:
        p8 = 1 if gm_curr > gm_prior else 0
    details["gross_margin_increasing"] = p8

    # 9. Asset turnover increasing
    at_curr = _safe_div(current.get("revenue"), ta_curr)
    at_prior = _safe_div(prior.get("revenue"), ta_prior)
    p9 = 0
    if at_curr is not None and at_prior is not None:
        p9 = 1 if at_curr > at_prior else 0
    details["asset_turnover_increasing"] = p9

    efficiency = p8 + p9

    score = profitability + leverage + efficiency

    if score >= 7:
        strength = "strong"
    elif score >= 4:
        strength = "average"
    else:
        strength = "weak"

    return {
        "fscore": score,
        "strength": strength,
        "profitability": profitability,
        "leverage_liquidity": leverage,
        "operating_efficiency": efficiency,
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate Piotroski F-Score")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("--market", help="Market code (US/TW/CN)")

    args = parser.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
    from fetcher_factory import get_fetcher, detect_market

    market = args.market or detect_market(args.ticker)
    fetcher = get_fetcher(market)

    # Get last 2 years of financials
    financials_list = fetcher.get_financials(args.ticker, period="annual")
    if len(financials_list) < 2:
        print(f"Need at least 2 years of financial data for {args.ticker}")
        sys.exit(1)

    current = financials_list[0]
    prior = financials_list[1]

    result = calculate_fscore(current, prior)
    result["ticker"] = args.ticker.upper()
    result["market"] = market
    result["current_period"] = current.get("period_date", "unknown")
    result["prior_period"] = prior.get("period_date", "unknown")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
