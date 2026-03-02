#!/usr/bin/env python3
"""
Key financial ratios calculator.

Calculates and rates key financial ratios for stock analysis.

Usage:
    python ratios.py AAPL --market US
    python ratios.py 2330 --market TW
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
from fetcher_factory import get_fetcher, detect_market


# Rating thresholds: (metric, lower_is_better, thresholds)
# thresholds: [(max_for_5star, max_for_4star, max_for_3star, max_for_2star)]
RATING_RULES = {
    "pe_ratio": {
        "lower_is_better": True,
        "thresholds": [10, 15, 20, 30],  # ≤10: 5★, ≤15: 4★, ≤20: 3★, ≤30: 2★, >30: 1★
        "label_zh": "本益比 (P/E)",
    },
    "pb_ratio": {
        "lower_is_better": True,
        "thresholds": [1.0, 1.5, 3.0, 5.0],
        "label_zh": "股價淨值比 (P/B)",
    },
    "roe": {
        "lower_is_better": False,
        "thresholds": [0.25, 0.20, 0.15, 0.10],  # ≥25%: 5★, ≥20%: 4★, etc.
        "label_zh": "股東權益報酬率 (ROE)",
    },
    "roa": {
        "lower_is_better": False,
        "thresholds": [0.15, 0.10, 0.05, 0.02],
        "label_zh": "資產報酬率 (ROA)",
    },
    "de_ratio": {
        "lower_is_better": True,
        "thresholds": [30, 50, 100, 200],  # yfinance returns as percentage
        "label_zh": "負債權益比 (D/E)",
    },
    "current_ratio": {
        "lower_is_better": False,
        "thresholds": [3.0, 2.0, 1.5, 1.0],
        "label_zh": "流動比率",
    },
    "gross_margin": {
        "lower_is_better": False,
        "thresholds": [0.60, 0.40, 0.25, 0.15],
        "label_zh": "毛利率",
    },
    "operating_margin": {
        "lower_is_better": False,
        "thresholds": [0.30, 0.20, 0.10, 0.05],
        "label_zh": "營業利益率",
    },
    "net_margin": {
        "lower_is_better": False,
        "thresholds": [0.25, 0.15, 0.08, 0.03],
        "label_zh": "淨利率",
    },
    "dividend_yield": {
        "lower_is_better": False,
        "thresholds": [0.05, 0.04, 0.03, 0.02],
        "label_zh": "殖利率",
    },
}


def rate_metric(metric_name: str, value: float | None) -> int:
    """Rate a metric on a 1-5 scale. Returns 0 if value is None."""
    if value is None:
        return 0

    rules = RATING_RULES.get(metric_name)
    if not rules:
        return 0

    thresholds = rules["thresholds"]
    lower_is_better = rules["lower_is_better"]

    if lower_is_better:
        for i, threshold in enumerate(thresholds):
            if value <= threshold:
                return 5 - i
        return 1
    else:
        for i, threshold in enumerate(thresholds):
            if value >= threshold:
                return 5 - i
        return 1


def calculate_ratios(metrics: dict) -> dict:
    """Calculate and rate financial ratios.

    Args:
        metrics: dict from fetcher.get_key_metrics()

    Returns:
        dict with ratios, ratings, and formatted output
    """
    results = {}
    for metric_name, rules in RATING_RULES.items():
        value = metrics.get(metric_name)
        rating = rate_metric(metric_name, value)

        # Format value for display
        if value is not None:
            if metric_name in ("roe", "roa", "gross_margin", "operating_margin",
                               "net_margin", "dividend_yield"):
                display = f"{value * 100:.1f}%" if abs(value) < 1 else f"{value:.1f}%"
            else:
                display = f"{value:.2f}"
        else:
            display = "N/A"

        results[metric_name] = {
            "value": value,
            "display": display,
            "rating": rating,
            "stars": "★" * rating + "☆" * (5 - rating) if rating > 0 else "N/A",
            "label_zh": rules["label_zh"],
        }

    # Overall rating (average of available ratings)
    ratings = [r["rating"] for r in results.values() if r["rating"] > 0]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    return {
        "ratios": results,
        "overall_rating": round(avg_rating, 1),
        "rated_metrics": len(ratings),
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate key financial ratios")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("--market", help="Market code (US/TW/CN)")

    args = parser.parse_args()
    market = args.market or detect_market(args.ticker)
    fetcher = get_fetcher(market)

    metrics = fetcher.get_key_metrics(args.ticker)
    result = calculate_ratios(metrics)
    result["ticker"] = args.ticker.upper()
    result["market"] = market

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
