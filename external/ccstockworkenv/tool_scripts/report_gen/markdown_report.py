#!/usr/bin/env python3
"""
Markdown report generator for CCStockWorkEnv.

Generates structured research reports in 繁體中文.

Usage:
    python markdown_report.py --type single --ticker AAPL --market US --output ../../output/
    python markdown_report.py --type comparison --tickers AAPL,MSFT --market US --output ../../output/
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "market_data"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "financial_calc"))

from fetcher_factory import get_fetcher, detect_market


def _format_number(value, prefix="", suffix="", decimals=2):
    """Format a number for display."""
    if value is None:
        return "N/A"
    if abs(value) >= 1e12:
        return f"{prefix}{value/1e12:.{decimals}f}T{suffix}"
    if abs(value) >= 1e9:
        return f"{prefix}{value/1e9:.{decimals}f}B{suffix}"
    if abs(value) >= 1e6:
        return f"{prefix}{value/1e6:.{decimals}f}M{suffix}"
    return f"{prefix}{value:,.{decimals}f}{suffix}"


def _format_pct(value, decimals=1):
    """Format a value as percentage."""
    if value is None:
        return "N/A"
    if abs(value) < 1:  # Already decimal (0.15 = 15%)
        return f"{value*100:.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def generate_single_report(ticker: str, market: str, output_dir: str) -> str:
    """Generate a single stock deep dive report."""
    os.makedirs(output_dir, exist_ok=True)

    fetcher = get_fetcher(market)
    info = fetcher.get_company_info(ticker)
    metrics = fetcher.get_key_metrics(ticker)
    quote = fetcher.get_quote(ticker)
    financials = fetcher.get_financials(ticker, period="annual")

    # Z-Score
    from zscore import calculate_zscore
    zscore_result = {"zscore": None, "zone": "N/A"}
    if financials:
        latest_fin = financials[0].copy()
        latest_fin["market_cap"] = metrics.get("market_cap", 0)
        zscore_result = calculate_zscore(latest_fin)

    # F-Score
    from fscore import calculate_fscore
    fscore_result = {"fscore": "N/A", "strength": "N/A"}
    if len(financials) >= 2:
        fscore_result = calculate_fscore(financials[0], financials[1])

    # Build report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    report = f"""# {info.name} ({ticker}) — 個股研究報告

> 產生時間：{timestamp}
> 市場：{market} | 貨幣：{info.currency or 'N/A'}

---

## 公司概要

- **名稱**：{info.name}
- **產業**：{info.sector or 'N/A'} / {info.industry or 'N/A'}
- **交易所**：{info.exchange or 'N/A'}
- **員工數**：{info.employees or 'N/A'}
- **國家**：{info.country or 'N/A'}

---

## 即時行情

| 項目 | 數值 |
|------|------|
| 現價 | {_format_number(quote.price)} |
| 漲跌 | {quote.change:+.2f} ({quote.change_pct:+.2f}%) |
| 開盤 | {_format_number(quote.open)} |
| 最高 | {_format_number(quote.high)} |
| 最低 | {_format_number(quote.low)} |
| 成交量 | {_format_number(quote.volume, decimals=0)} |

---

## 關鍵指標

| 指標 | 數值 |
|------|------|
| 市值 | {_format_number(metrics.get('market_cap'))} |
| 本益比 (P/E) | {_format_number(metrics.get('pe_ratio'))} |
| 股價淨值比 (P/B) | {_format_number(metrics.get('pb_ratio'))} |
| ROE | {_format_pct(metrics.get('roe'))} |
| ROA | {_format_pct(metrics.get('roa'))} |
| 負債權益比 (D/E) | {_format_number(metrics.get('de_ratio'))} |
| 毛利率 | {_format_pct(metrics.get('gross_margin'))} |
| 營業利益率 | {_format_pct(metrics.get('operating_margin'))} |
| 淨利率 | {_format_pct(metrics.get('net_margin'))} |
| 殖利率 | {_format_pct(metrics.get('dividend_yield'))} |
| 52週最高 | {_format_number(metrics.get('fifty_two_week_high'))} |
| 52週最低 | {_format_number(metrics.get('fifty_two_week_low'))} |

---

## 健康評估

### Altman Z-Score：{_format_number(zscore_result.get('zscore'))}
- **判定**：{ {'safe': '安全區', 'grey': '灰色地帶', 'distress': '危險區'}.get(zscore_result.get('zone'), 'N/A') }

### Piotroski F-Score：{fscore_result.get('fscore', 'N/A')}/9
- **判定**：{ {'strong': '財務強健', 'average': '普通', 'weak': '疲弱'}.get(fscore_result.get('strength'), 'N/A') }

---

## 財務趨勢

"""

    if financials:
        # Build financial table (last 4 years)
        periods = financials[:4]
        headers = " | ".join([p.get("period_date", "")[:4] for p in periods])
        report += f"| 項目 | {headers} |\n"
        report += "|------|" + "|".join(["------|"] * len(periods)) + "\n"

        for label, key in [
            ("營收", "revenue"),
            ("毛利", "gross_profit"),
            ("營業利益", "operating_income"),
            ("淨利", "net_income"),
            ("EPS", "eps"),
            ("營業現金流", "operating_cash_flow"),
            ("自由現金流", "fcf"),
        ]:
            values = " | ".join([_format_number(p.get(key)) for p in periods])
            report += f"| {label} | {values} |\n"

    report += f"""
---

## 免責聲明

本報告僅供研究參考，不構成投資建議。投資有風險，請自行評估後做出決策。

---
*報告由 CCStockWorkEnv 自動產生 — {timestamp}*
"""

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{ticker}_{market}_report.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    return filepath


def generate_comparison_report(tickers: list[str], market: str, output_dir: str) -> str:
    """Generate a stock comparison report."""
    os.makedirs(output_dir, exist_ok=True)

    fetcher = get_fetcher(market)
    stocks_data = []
    for ticker in tickers:
        info = fetcher.get_company_info(ticker)
        metrics = fetcher.get_key_metrics(ticker)
        quote = fetcher.get_quote(ticker)
        stocks_data.append({"ticker": ticker, "info": info, "metrics": metrics, "quote": quote})

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    ticker_str = " vs ".join(tickers)

    report = f"""# 股票比較報告：{ticker_str}

> 產生時間：{timestamp}
> 市場：{market}

---

## 比較總覽

| 指標 | {' | '.join(tickers)} |
|------|{'|'.join(['------|'] * len(tickers))}
"""

    metrics_list = [
        ("現價", lambda d: _format_number(d["quote"].price)),
        ("漲跌%", lambda d: f"{d['quote'].change_pct:+.2f}%"),
        ("市值", lambda d: _format_number(d["metrics"].get("market_cap"))),
        ("P/E", lambda d: _format_number(d["metrics"].get("pe_ratio"))),
        ("P/B", lambda d: _format_number(d["metrics"].get("pb_ratio"))),
        ("ROE", lambda d: _format_pct(d["metrics"].get("roe"))),
        ("ROA", lambda d: _format_pct(d["metrics"].get("roa"))),
        ("D/E", lambda d: _format_number(d["metrics"].get("de_ratio"))),
        ("毛利率", lambda d: _format_pct(d["metrics"].get("gross_margin"))),
        ("營業利益率", lambda d: _format_pct(d["metrics"].get("operating_margin"))),
        ("淨利率", lambda d: _format_pct(d["metrics"].get("net_margin"))),
        ("殖利率", lambda d: _format_pct(d["metrics"].get("dividend_yield"))),
        ("52週高", lambda d: _format_number(d["metrics"].get("fifty_two_week_high"))),
        ("52週低", lambda d: _format_number(d["metrics"].get("fifty_two_week_low"))),
    ]

    for label, fn in metrics_list:
        values = " | ".join([fn(d) for d in stocks_data])
        report += f"| {label} | {values} |\n"

    report += f"""
---

## 免責聲明

本報告僅供研究參考，不構成投資建議。

---
*報告由 CCStockWorkEnv 自動產生 — {timestamp}*
"""

    ticker_label = "_".join(tickers[:3])
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_comparison_{ticker_label}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    return filepath


def main():
    parser = argparse.ArgumentParser(description="Generate CCStockWorkEnv reports")
    parser.add_argument("--type", required=True, choices=["single", "comparison"],
                        help="Report type")
    parser.add_argument("--ticker", help="Stock ticker (for single)")
    parser.add_argument("--tickers", help="Comma-separated tickers (for comparison)")
    parser.add_argument("--market", help="Market code")
    parser.add_argument("--output", default="../../output/", help="Output directory")

    args = parser.parse_args()

    if args.type == "single":
        market = args.market or detect_market(args.ticker)
        path = generate_single_report(args.ticker, market, args.output)
        print(f"Report saved: {path}")

    elif args.type == "comparison":
        tickers = args.tickers.split(",")
        market = args.market or detect_market(tickers[0])
        path = generate_comparison_report(tickers, market, args.output)
        print(f"Report saved: {path}")


if __name__ == "__main__":
    main()
