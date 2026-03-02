#!/usr/bin/env python3
"""
Chart generator for CCStockWorkEnv reports.

Generates matplotlib charts for stock analysis.

Usage:
    python chart_gen.py --type price --ticker AAPL --market US --output ../../data/charts/
    python chart_gen.py --type comparison --tickers AAPL,MSFT,GOOGL --market US --output ../../data/charts/
    python chart_gen.py --type financials --ticker AAPL --market US --output ../../data/charts/
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
from fetcher_factory import get_fetcher, detect_market
from fetcher_base import PriceRecord


def _ensure_output_dir(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)


def generate_price_chart(ticker: str, market: str, days: int = 365,
                         output_dir: str = "../../data/charts/") -> str:
    """Generate a price history line chart."""
    _ensure_output_dir(output_dir)
    fetcher = get_fetcher(market)

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    history = fetcher.get_price_history(ticker, start, end)

    if not history:
        print(f"No price data for {ticker}", file=sys.stderr)
        return ""

    dates = [datetime.strptime(r.date, "%Y-%m-%d") for r in history]
    closes = [r.close for r in history]
    volumes = [r.volume for r in history]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1],
                                     sharex=True)

    # Price chart
    ax1.plot(dates, closes, color="#2196F3", linewidth=1.5)
    ax1.fill_between(dates, closes, alpha=0.1, color="#2196F3")
    ax1.set_title(f"{ticker} ({market}) — Price History", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Price", fontsize=12)
    ax1.grid(True, alpha=0.3)

    # Volume chart
    ax2.bar(dates, volumes, color="#90CAF9", alpha=0.7, width=1)
    ax2.set_ylabel("Volume", fontsize=12)
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45)
    plt.tight_layout()

    filename = f"{ticker}_{market}_price_{datetime.now().strftime('%Y%m%d')}.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return filepath


def generate_comparison_chart(tickers: list[str], market: str, days: int = 365,
                              output_dir: str = "../../data/charts/") -> str:
    """Generate a normalized price comparison chart for multiple stocks."""
    _ensure_output_dir(output_dir)

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ["#2196F3", "#F44336", "#4CAF50", "#FF9800", "#9C27B0"]

    for i, ticker in enumerate(tickers):
        fetcher = get_fetcher(market)
        history = fetcher.get_price_history(ticker, start, end)
        if not history:
            continue

        dates = [datetime.strptime(r.date, "%Y-%m-%d") for r in history]
        closes = [r.close for r in history]

        # Normalize to 100
        base = closes[0] if closes else 1
        normalized = [(c / base) * 100 for c in closes]

        ax.plot(dates, normalized, label=ticker, color=colors[i % len(colors)], linewidth=1.5)

    ax.set_title(f"Price Comparison (Normalized)", fontsize=14, fontweight="bold")
    ax.set_ylabel("Normalized Price (Base=100)", fontsize=12)
    ax.axhline(y=100, color="gray", linestyle="--", alpha=0.5)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45)
    plt.tight_layout()

    ticker_str = "_".join(tickers[:3])
    filename = f"comparison_{ticker_str}_{datetime.now().strftime('%Y%m%d')}.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return filepath


def generate_financials_chart(ticker: str, market: str,
                              output_dir: str = "../../data/charts/") -> str:
    """Generate a financial metrics bar chart (revenue, net income, FCF)."""
    _ensure_output_dir(output_dir)
    fetcher = get_fetcher(market)

    financials = fetcher.get_financials(ticker, period="annual")
    if not financials:
        print(f"No financial data for {ticker}", file=sys.stderr)
        return ""

    # Take last 5 years, reverse for chronological order
    data = list(reversed(financials[:5]))

    periods = [d.get("period_date", "")[:4] for d in data]
    revenue = [d.get("revenue", 0) or 0 for d in data]
    net_income = [d.get("net_income", 0) or 0 for d in data]
    fcf = [d.get("fcf", 0) or 0 for d in data]

    # Scale to billions/millions
    max_val = max(max(abs(v) for v in revenue), 1)
    if max_val >= 1e9:
        scale = 1e9
        unit = "B"
    elif max_val >= 1e6:
        scale = 1e6
        unit = "M"
    else:
        scale = 1
        unit = ""

    revenue_s = [v / scale for v in revenue]
    ni_s = [v / scale for v in net_income]
    fcf_s = [v / scale for v in fcf]

    x = range(len(periods))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([i - width for i in x], revenue_s, width, label="Revenue", color="#2196F3")
    ax.bar(x, ni_s, width, label="Net Income", color="#4CAF50")
    ax.bar([i + width for i in x], fcf_s, width, label="FCF", color="#FF9800")

    ax.set_title(f"{ticker} ({market}) — Financial Overview", fontsize=14, fontweight="bold")
    ax.set_ylabel(f"Amount ({unit})", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(periods)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")
    ax.axhline(y=0, color="gray", linewidth=0.5)
    plt.tight_layout()

    filename = f"{ticker}_{market}_financials_{datetime.now().strftime('%Y%m%d')}.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return filepath


def generate_radar_chart(ticker: str, metrics: dict,
                         output_dir: str = "../../data/charts/") -> str:
    """Generate a radar chart for key metrics."""
    _ensure_output_dir(output_dir)
    import numpy as np

    categories = ["Value", "Quality", "Safety", "Momentum", "Income"]
    values = [
        metrics.get("value", {}).get("score", 50),
        metrics.get("quality", {}).get("score", 50),
        metrics.get("safety", {}).get("score", 50),
        metrics.get("momentum", {}).get("score", 50),
        metrics.get("income", {}).get("score", 50),
    ]

    # Close the radar
    values += values[:1]
    angles = [n / float(len(categories)) * 2 * 3.14159 for n in range(len(categories))]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.plot(angles, values, "o-", linewidth=2, color="#2196F3")
    ax.fill(angles, values, alpha=0.15, color="#2196F3")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=12)
    ax.set_ylim(0, 100)
    ax.set_title(f"{ticker} — Opportunity Score Breakdown", fontsize=14, fontweight="bold", pad=20)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    filename = f"{ticker}_radar_{datetime.now().strftime('%Y%m%d')}.png"
    filepath = os.path.join(output_dir, filename)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close()

    return filepath


def main():
    parser = argparse.ArgumentParser(description="Generate charts for stock analysis")
    parser.add_argument("--type", required=True,
                        choices=["price", "comparison", "financials", "radar"],
                        help="Chart type")
    parser.add_argument("--ticker", help="Stock ticker (for single stock charts)")
    parser.add_argument("--tickers", help="Comma-separated tickers (for comparison)")
    parser.add_argument("--market", help="Market code (US/TW/CN)")
    parser.add_argument("--days", type=int, default=365, help="Days of history")
    parser.add_argument("--output", default="../../data/charts/", help="Output directory")

    args = parser.parse_args()

    if args.type == "price":
        market = args.market or detect_market(args.ticker)
        path = generate_price_chart(args.ticker, market, days=args.days, output_dir=args.output)
        print(f"Chart saved: {path}")

    elif args.type == "comparison":
        tickers = args.tickers.split(",")
        market = args.market or detect_market(tickers[0])
        path = generate_comparison_chart(tickers, market, days=args.days, output_dir=args.output)
        print(f"Chart saved: {path}")

    elif args.type == "financials":
        market = args.market or detect_market(args.ticker)
        path = generate_financials_chart(args.ticker, market, output_dir=args.output)
        print(f"Chart saved: {path}")

    elif args.type == "radar":
        print("Radar chart requires opportunity score data. Use via report generator.")


if __name__ == "__main__":
    main()
