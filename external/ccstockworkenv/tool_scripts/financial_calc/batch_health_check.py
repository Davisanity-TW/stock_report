#!/usr/bin/env python3
"""
Batch health check for CN stock candidates at 3-year lows.

Runs Z-Score, F-Score, key ratios, opportunity score, and value trap detection
on all candidates from the low-point screening.

Usage:
    python batch_health_check.py
"""

import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "db_ops"))

from fetcher_factory import get_fetcher
from db_manager import get_connection, DB_PATH
from zscore import calculate_zscore
from fscore import calculate_fscore


def get_candidates():
    """Get all CN stocks at ≤60% of 3-year high from DB."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            s.ticker, s.name,
            latest.close AS current_price,
            stats.period_high AS three_year_high,
            ROUND(latest.close / stats.period_high * 100, 1) AS pct_of_high,
            stats.period_low AS three_year_low
        FROM stocks s
        JOIN (
            SELECT ticker, market, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker, market ORDER BY date DESC) AS rn
            FROM daily_prices WHERE market = 'CN'
        ) latest ON s.ticker = latest.ticker AND s.market = latest.market AND latest.rn = 1
        JOIN (
            SELECT ticker, market, MAX(high) AS period_high, MIN(low) AS period_low
            FROM daily_prices WHERE market = 'CN' AND date >= date('now', '-3 years')
            GROUP BY ticker, market
        ) stats ON s.ticker = stats.ticker AND s.market = stats.market
        WHERE s.market = 'CN' AND s.is_active = 1
          AND latest.close <= stats.period_high * 0.60 AND latest.close > 0
        ORDER BY pct_of_high ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_value_trap(financials_list):
    """Check for value trap indicators.

    Returns dict with trap indicators and overall verdict.
    """
    traps = []

    if len(financials_list) < 2:
        return {"traps": ["insufficient_data"], "is_trap": None}

    current = financials_list[0]
    prior = financials_list[1]

    # 1. Declining revenue (current vs prior)
    rev_curr = current.get("revenue")
    rev_prior = prior.get("revenue")
    if rev_curr and rev_prior and rev_prior > 0:
        rev_growth = (rev_curr - rev_prior) / abs(rev_prior)
        if rev_growth < -0.10:  # >10% decline
            traps.append(f"revenue_declining ({rev_growth*100:.1f}%)")

    # 2. Negative FCF (both years)
    fcf_curr = current.get("fcf")
    fcf_prior = prior.get("fcf")
    if fcf_curr is not None and fcf_prior is not None:
        if fcf_curr < 0 and fcf_prior < 0:
            traps.append("negative_fcf_2yr")

    # 3. Increasing D/E with declining revenue
    ta_curr = current.get("total_assets") or 1
    ta_prior = prior.get("total_assets") or 1
    tl_curr = current.get("total_liabilities") or 0
    tl_prior = prior.get("total_liabilities") or 0
    eq_curr = current.get("total_equity") or 1
    eq_prior = prior.get("total_equity") or 1

    if eq_curr > 0 and eq_prior > 0:
        de_curr = tl_curr / eq_curr
        de_prior = tl_prior / eq_prior
        if de_curr > de_prior and rev_curr and rev_prior and rev_curr < rev_prior:
            traps.append("debt_spiral")

    # 4. Negative net income
    ni_curr = current.get("net_income")
    if ni_curr is not None and ni_curr < 0:
        traps.append("net_loss")

    return {
        "traps": traps,
        "trap_count": len(traps),
        "is_trap": len(traps) >= 2,
    }


def run_batch_health_check():
    """Run health checks on all candidates."""
    candidates = get_candidates()
    print(f"Running health check on {len(candidates)} candidates...\n")

    fetcher = get_fetcher("CN")
    results = []

    for i, candidate in enumerate(candidates):
        ticker = candidate["ticker"]
        name = candidate["name"]
        print(f"[{i+1}/{len(candidates)}] {ticker} {name} ({candidate['pct_of_high']}% of 3yr high)")

        result = {
            "ticker": ticker,
            "name": name,
            "current_price": candidate["current_price"],
            "three_year_high": candidate["three_year_high"],
            "pct_of_high": candidate["pct_of_high"],
            "three_year_low": candidate["three_year_low"],
        }

        try:
            # Get financials
            financials = fetcher.get_financials(ticker, period="annual")
            metrics = fetcher.get_key_metrics(ticker)

            # Z-Score
            if financials:
                latest_fin = financials[0].copy()
                latest_fin["market_cap"] = metrics.get("market_cap", 0)
                zscore_result = calculate_zscore(latest_fin)
                result["zscore"] = zscore_result.get("zscore")
                result["zscore_zone"] = zscore_result.get("zone")
            else:
                result["zscore"] = None
                result["zscore_zone"] = "no_data"

            # F-Score
            if len(financials) >= 2:
                fscore_result = calculate_fscore(financials[0], financials[1])
                result["fscore"] = fscore_result.get("fscore")
                result["fscore_strength"] = fscore_result.get("strength")
            else:
                result["fscore"] = None
                result["fscore_strength"] = "no_data"

            # Key metrics
            result["pe_ratio"] = metrics.get("pe_ratio")
            result["pb_ratio"] = metrics.get("pb_ratio")
            result["roe"] = metrics.get("roe")
            result["roa"] = metrics.get("roa")
            result["de_ratio"] = metrics.get("de_ratio")
            result["current_ratio"] = metrics.get("current_ratio")
            result["gross_margin"] = metrics.get("gross_margin")
            result["net_margin"] = metrics.get("net_margin")
            result["dividend_yield"] = metrics.get("dividend_yield")
            result["market_cap"] = metrics.get("market_cap")

            # Value trap detection
            trap_result = check_value_trap(financials)
            result["value_traps"] = trap_result["traps"]
            result["trap_count"] = trap_result["trap_count"]
            result["is_trap"] = trap_result["is_trap"]

            # Classification (from financial_analysis.md skill)
            # PASS: Z > 1.81, F >= 4, current_ratio > 1.0
            z = result["zscore"]
            f = result["fscore"]
            cr = result["current_ratio"]

            passes_basic = (
                (z is not None and z > 1.81) and
                (f is not None and f >= 4) and
                (cr is not None and cr > 1.0)
            )

            # STRONG: Z > 2.99, F >= 7, ROE > 10%, D/E < 100
            roe = result["roe"]
            de = result["de_ratio"]
            is_strong = passes_basic and (
                (z is not None and z > 2.99) and
                (f is not None and f >= 7) and
                (roe is not None and roe > 0.10) and
                (de is not None and de < 100)
            )

            if is_strong and not result.get("is_trap"):
                result["classification"] = "STRONG"
            elif passes_basic and not result.get("is_trap"):
                result["classification"] = "PASS"
            elif passes_basic and result.get("trap_count", 0) == 1:
                result["classification"] = "WATCH"
            else:
                result["classification"] = "EXCLUDE"

            print(f"  → Z={z}, F={f}, class={result['classification']}, traps={result['value_traps']}")

        except Exception as e:
            result["classification"] = "ERROR"
            result["error"] = str(e)
            print(f"  → ERROR: {e}")

        results.append(result)
        time.sleep(1.5)  # Rate limit yfinance

    # Save results
    output_path = os.path.join(os.path.dirname(__file__), "_health_check_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    strong = [r for r in results if r.get("classification") == "STRONG"]
    passed = [r for r in results if r.get("classification") == "PASS"]
    watch = [r for r in results if r.get("classification") == "WATCH"]
    excluded = [r for r in results if r.get("classification") == "EXCLUDE"]
    errored = [r for r in results if r.get("classification") == "ERROR"]

    print(f"⭐ STRONG:   {len(strong)}")
    print(f"✅ PASS:     {len(passed)}")
    print(f"⚠️  WATCH:    {len(watch)}")
    print(f"❌ EXCLUDE:  {len(excluded)}")
    print(f"💥 ERROR:    {len(errored)}")

    if strong:
        print(f"\n⭐ STRONG candidates:")
        for r in strong:
            print(f"  {r['ticker']} {r['name']}: Z={r.get('zscore')}, F={r.get('fscore')}, "
                  f"ROE={r.get('roe')}, price={r['pct_of_high']}% of 3yr high")

    if passed:
        print(f"\n✅ PASS candidates:")
        for r in passed:
            print(f"  {r['ticker']} {r['name']}: Z={r.get('zscore')}, F={r.get('fscore')}, "
                  f"price={r['pct_of_high']}% of 3yr high")

    if watch:
        print(f"\n⚠️  WATCH candidates:")
        for r in watch:
            print(f"  {r['ticker']} {r['name']}: traps={r.get('value_traps')}, "
                  f"price={r['pct_of_high']}% of 3yr high")

    return results


if __name__ == "__main__":
    run_batch_health_check()
