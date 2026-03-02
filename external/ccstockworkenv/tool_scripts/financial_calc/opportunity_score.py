#!/usr/bin/env python3
"""
Weighted Opportunity Score calculator.

Combines multiple financial metrics into a single composite score (0-100)
to identify investment opportunities.

Weights:
    - Value (30%): P/E, P/B relative to peers/history
    - Quality (25%): ROE, ROA, margins
    - Safety (20%): Z-Score, D/E, current ratio
    - Momentum (15%): Price vs N-year high/low, trend
    - Income (10%): Dividend yield, FCF yield

Usage:
    python opportunity_score.py AAPL --market US
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
from fetcher_factory import get_fetcher, detect_market
from zscore import calculate_zscore
from fscore import calculate_fscore


def _score_range(value, min_val, max_val, invert=False):
    """Score a value on 0-100 scale within a range. Invert if lower is better."""
    if value is None:
        return 50  # Neutral default
    clamped = max(min_val, min(max_val, value))
    normalized = (clamped - min_val) / (max_val - min_val) if max_val != min_val else 0
    return round((1 - normalized if invert else normalized) * 100)


def calculate_opportunity_score(metrics: dict, zscore_data: dict = None,
                                 fscore_data: dict = None,
                                 price_vs_high: float = None) -> dict:
    """Calculate weighted opportunity score.

    Args:
        metrics: Key metrics from fetcher.get_key_metrics()
        zscore_data: Result from calculate_zscore() (optional)
        fscore_data: Result from calculate_fscore() (optional)
        price_vs_high: Current price as % of N-year high (optional, 0-100)

    Returns:
        dict with total score, category scores, and breakdown
    """
    breakdown = {}

    # === Value Score (30%) ===
    pe = metrics.get("pe_ratio")
    pb = metrics.get("pb_ratio")

    pe_score = _score_range(pe, 5, 40, invert=True) if pe and pe > 0 else 50
    pb_score = _score_range(pb, 0.5, 5, invert=True) if pb and pb > 0 else 50
    value_score = (pe_score * 0.6 + pb_score * 0.4)
    breakdown["value"] = {"score": round(value_score), "weight": 0.30,
                           "pe_score": pe_score, "pb_score": pb_score}

    # === Quality Score (25%) ===
    roe = metrics.get("roe")
    roa = metrics.get("roa")
    gm = metrics.get("gross_margin")
    nm = metrics.get("net_margin")

    roe_score = _score_range(roe, 0, 0.30) if roe else 50
    roa_score = _score_range(roa, 0, 0.20) if roa else 50
    gm_score = _score_range(gm, 0, 0.60) if gm else 50
    nm_score = _score_range(nm, 0, 0.25) if nm else 50

    quality_score = (roe_score * 0.35 + roa_score * 0.25 + gm_score * 0.20 + nm_score * 0.20)
    breakdown["quality"] = {"score": round(quality_score), "weight": 0.25}

    # === Safety Score (20%) ===
    de = metrics.get("de_ratio")
    cr = metrics.get("current_ratio")

    de_score = _score_range(de, 0, 200, invert=True) if de else 50
    cr_score = _score_range(cr, 0.5, 3.0) if cr else 50

    zscore_score = 50
    if zscore_data and zscore_data.get("zscore") is not None:
        zscore_score = _score_range(zscore_data["zscore"], 0, 4)

    safety_score = (de_score * 0.30 + cr_score * 0.30 + zscore_score * 0.40)
    breakdown["safety"] = {"score": round(safety_score), "weight": 0.20}

    # === Momentum Score (15%) ===
    momentum_score = 50
    if price_vs_high is not None:
        # Lower price vs high = better opportunity (contrarian)
        momentum_score = _score_range(price_vs_high, 30, 100, invert=True)

    fscore_bonus = 0
    if fscore_data:
        fscore_bonus = (fscore_data["fscore"] / 9) * 100

    momentum_score = momentum_score * 0.6 + fscore_bonus * 0.4
    breakdown["momentum"] = {"score": round(momentum_score), "weight": 0.15}

    # === Income Score (10%) ===
    dy = metrics.get("dividend_yield")
    dy_score = _score_range(dy, 0, 0.06) if dy else 30
    breakdown["income"] = {"score": round(dy_score), "weight": 0.10}

    # === Total Score ===
    total = (
        value_score * 0.30
        + quality_score * 0.25
        + safety_score * 0.20
        + momentum_score * 0.15
        + dy_score * 0.10
    )

    if total >= 75:
        verdict = "strong_opportunity"
    elif total >= 60:
        verdict = "moderate_opportunity"
    elif total >= 40:
        verdict = "neutral"
    else:
        verdict = "caution"

    return {
        "opportunity_score": round(total, 1),
        "verdict": verdict,
        "breakdown": breakdown,
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate Opportunity Score")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("--market", help="Market code (US/TW/CN)")

    args = parser.parse_args()
    market = args.market or detect_market(args.ticker)
    fetcher = get_fetcher(market)

    # Get all data
    metrics = fetcher.get_key_metrics(args.ticker)
    financials = fetcher.get_financials(args.ticker, period="annual")

    # Z-Score
    zscore_data = None
    if financials:
        latest = financials[0]
        latest["market_cap"] = metrics.get("market_cap", 0)
        zscore_data = calculate_zscore(latest)

    # F-Score
    fscore_data = None
    if len(financials) >= 2:
        fscore_data = calculate_fscore(financials[0], financials[1])

    # Price vs high
    price_vs_high = None
    high_52w = metrics.get("fifty_two_week_high")
    quote = fetcher.get_quote(args.ticker)
    if high_52w and quote.price:
        price_vs_high = (quote.price / high_52w) * 100

    result = calculate_opportunity_score(metrics, zscore_data, fscore_data, price_vs_high)
    result["ticker"] = args.ticker.upper()
    result["market"] = market

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
