#!/usr/bin/env python3
"""
Batch download China A-share data using yfinance fallback.

AKShare (East Money API) is inaccessible from outside mainland China.
This script uses yfinance as the fallback, per the plan's risk mitigation.

Strategy:
1. Build a comprehensive CN ticker list from multiple index components
2. Use yfinance to get current prices + 3-year history in bulk
3. Store in SQLite

Usage:
    python batch_cn_yfinance.py --step tickers     # Step 1: Build ticker list
    python batch_cn_yfinance.py --step history      # Step 2: Download 3yr history
    python batch_cn_yfinance.py --step all          # Run all steps
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "db_ops"))
from db_manager import get_connection, DB_PATH
from stock_ops import bulk_add_stocks, add_stock
from price_ops import bulk_upsert_prices

# Major China A-share index components and blue chips
# Covering: CSI 300 core, SSE 50, major sectors
# yfinance suffix: .SS (Shanghai), .SZ (Shenzhen)
CN_TICKERS = {
    # === Finance / Banking ===
    "601398": "工商银行", "601939": "建设银行", "601288": "农业银行",
    "601988": "中国银行", "600036": "招商银行", "601166": "兴业银行",
    "600016": "民生银行", "601328": "交通银行", "600000": "浦发银行",
    "002142": "宁波银行", "600015": "华夏银行", "601009": "南京银行",
    "601818": "光大银行", "600919": "江苏银行", "601838": "成都银行",
    # === Insurance ===
    "601318": "中国平安", "601628": "中国人寿", "601601": "中国太保",
    "600030": "中信证券", "601211": "国泰君安", "600837": "海通证券",
    # === Consumer / Liquor ===
    "600519": "贵州茅台", "000858": "五粮液", "000568": "泸州老窖",
    "600809": "山西汾酒", "002304": "洋河股份", "000799": "酒鬼酒",
    "603369": "今世缘", "000596": "古井贡酒", "600779": "水井坊",
    # === Consumer / Food & Beverage ===
    "600887": "伊利股份", "000895": "双汇发展", "603288": "海天味业",
    "002568": "百润股份", "600600": "青岛啤酒", "000568": "泸州老窖",
    "002557": "洽洽食品", "603711": "香飘飘",
    # === Technology / Semiconductors ===
    "688981": "中芯国际", "002371": "北方华创", "603501": "韦尔股份",
    "688008": "澜起科技", "300782": "卓胜微", "688012": "中微公司",
    "002049": "紫光国微", "300661": "圣邦股份",
    # === Technology / Internet & Software ===
    "002230": "科大讯飞", "300033": "同花顺", "300496": "中科创达",
    "688111": "金山办公", "603039": "泛微网络", "300454": "深信服",
    # === Electric Vehicles / New Energy ===
    "300750": "宁德时代", "002594": "比亚迪", "300274": "阳光电源",
    "601012": "隆基绿能", "600438": "通威股份", "002459": "晶澳科技",
    "688599": "天合光能", "300763": "锦浪科技", "300316": "晶盛机电",
    "002129": "中环股份", "600905": "三峡能源",
    # === Healthcare / Pharma ===
    "600276": "恒瑞医药", "000538": "云南白药", "600196": "复星医药",
    "300760": "迈瑞医疗", "300122": "智飞生物", "002007": "华兰生物",
    "300347": "泰格医药", "688235": "百济神州", "600085": "同仁堂",
    "000963": "华东医药", "002001": "新和成", "300015": "爱尔眼科",
    # === Real Estate ===
    "001979": "招商蛇口", "600048": "保利发展", "000002": "万科A",
    "600383": "金地集团", "000069": "华侨城A", "600606": "绿地控股",
    "002244": "滨江集团",
    # === Industrial / Manufacturing ===
    "600690": "海尔智家", "000333": "美的集团", "000651": "格力电器",
    "002032": "苏泊尔", "002508": "老板电器",
    # === Materials / Chemicals ===
    "600309": "万华化学", "002601": "龙蟒佰利", "600585": "海螺水泥",
    "601899": "紫金矿业", "600489": "中金黄金", "601600": "中国铝业",
    "000831": "五矿稀土",
    # === Transportation / Infrastructure ===
    "601111": "中国国航", "600029": "南方航空", "601006": "大秦铁路",
    "600009": "上海机场", "600115": "中国东航", "601021": "春秋航空",
    # === Telecom / Utilities ===
    "600941": "中国移动", "601728": "中国电信", "600050": "中国联通",
    "600900": "长江电力", "600023": "浙能电力", "600886": "国投电力",
    # === Defense / Military ===
    "600893": "航发动力", "601989": "中国重工", "000768": "中航飞机",
    "600760": "中航沈飞", "002179": "中航光电",
    # === Media / Entertainment ===
    "300413": "芒果超媒", "002624": "完美世界", "002555": "三七互娱",
    "603444": "吉比特",
    # === Auto ===
    "600104": "上汽集团", "000625": "长安汽车", "601238": "广汽集团",
    "002074": "国轩高科", "300014": "亿纬锂能",
    # === Misc Blue Chips ===
    "601888": "中国中免", "603259": "药明康德", "300124": "汇川技术",
    "002415": "海康威视", "000725": "京东方A", "601995": "中金公司",
    "600031": "三一重工", "002475": "立讯精密", "300059": "东方财富",
}


def _yf_symbol(ticker: str) -> str:
    """Convert CN ticker to yfinance symbol."""
    if ticker.startswith("6") or ticker.startswith("9"):
        return f"{ticker}.SS"
    else:
        return f"{ticker}.SZ"


def step_tickers():
    """Step 1: Save all tickers to database."""
    print("=" * 60)
    print(f"Step 1: Saving {len(CN_TICKERS)} CN stock tickers to database...")
    print("=" * 60)

    stocks = []
    for ticker, name in CN_TICKERS.items():
        exchange = "SSE" if ticker.startswith("6") else "SZSE"
        stocks.append({
            "ticker": ticker,
            "market": "CN",
            "name": name,
            "exchange": exchange,
            "currency": "CNY",
        })

    count = bulk_add_stocks(stocks)
    print(f"Saved {count} stocks to database")
    return stocks


def step_history():
    """Step 2: Download 3-year price history for all tickers via yfinance."""
    print("=" * 60)
    print("Step 2: Downloading 3-year price history via yfinance...")
    print("=" * 60)

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d")

    tickers_list = list(CN_TICKERS.keys())
    total = len(tickers_list)
    success = 0
    errors = 0
    total_records = 0

    # Process in batches of 20 (yfinance can handle multiple tickers)
    batch_size = 20
    for batch_start in range(0, total, batch_size):
        batch = tickers_list[batch_start:batch_start + batch_size]
        yf_symbols = [_yf_symbol(t) for t in batch]
        symbols_str = " ".join(yf_symbols)

        try:
            data = yf.download(
                symbols_str,
                start=start_date,
                end=end_date,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )

            for ticker in batch:
                yf_sym = _yf_symbol(ticker)
                try:
                    if len(batch) == 1:
                        ticker_data = data
                    else:
                        ticker_data = data[yf_sym]

                    if ticker_data.empty:
                        errors += 1
                        continue

                    records = []
                    for date, row in ticker_data.iterrows():
                        close_val = row.get("Close")
                        if close_val is None or str(close_val) == "nan":
                            continue
                        records.append({
                            "ticker": ticker,
                            "market": "CN",
                            "date": date.strftime("%Y-%m-%d"),
                            "open": round(float(row["Open"]), 4) if str(row.get("Open")) != "nan" else None,
                            "high": round(float(row["High"]), 4) if str(row.get("High")) != "nan" else None,
                            "low": round(float(row["Low"]), 4) if str(row.get("Low")) != "nan" else None,
                            "close": round(float(row["Close"]), 4),
                            "volume": int(row["Volume"]) if str(row.get("Volume")) != "nan" else None,
                            "adj_close": round(float(row["Adj Close"]), 4) if str(row.get("Adj Close")) != "nan" else None,
                        })

                    if records:
                        bulk_upsert_prices(records)
                        success += 1
                        total_records += len(records)
                    else:
                        errors += 1

                except Exception as e:
                    errors += 1
                    if errors <= 10:
                        print(f"  Error processing {ticker}: {e}")

        except Exception as e:
            errors += len(batch)
            print(f"  Batch error: {e}")

        # Progress
        done = min(batch_start + batch_size, total)
        print(f"  Progress: {done}/{total} ({success} ok, {errors} err, {total_records} records)")
        time.sleep(1)  # Rate limit between batches

    print(f"\nDone: {success}/{total} stocks downloaded, {errors} errors")
    print(f"Total price records: {total_records}")

    # Verify in DB
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM daily_prices WHERE market = 'CN'").fetchone()[0]
    stocks_with_data = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM daily_prices WHERE market = 'CN'"
    ).fetchone()[0]
    conn.close()
    print(f"DB total CN price records: {count}")
    print(f"DB CN stocks with price data: {stocks_with_data}")


def main():
    parser = argparse.ArgumentParser(description="Batch CN data download via yfinance")
    parser.add_argument("--step", required=True,
                        choices=["tickers", "history", "all"],
                        help="Which step to run")
    args = parser.parse_args()

    if args.step == "tickers" or args.step == "all":
        step_tickers()
    if args.step == "history" or args.step == "all":
        step_history()


if __name__ == "__main__":
    main()
