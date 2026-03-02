"""
China A-share market data fetcher using Yahoo Finance (yfinance).

Yahoo Finance provides reliable overseas access to Shanghai (SSE) and
Shenzhen (SZSE) stock data via ticker suffixes .SS and .SZ respectively.

AKShare was previously used but is unreliable from overseas due to
East Money (push2.eastmoney.com) blocking non-China IPs.
"""

from datetime import datetime

import yfinance as yf

from fetcher_base import MarketDataFetcher, StockQuote, CompanyInfo, PriceRecord


class CNFetcher(MarketDataFetcher):
    """China A-share market data fetcher via Yahoo Finance."""

    @property
    def market_code(self) -> str:
        return "CN"

    def detect_ticker(self, raw_ticker: str) -> str:
        """Normalize China ticker (6 digits, strip suffix)."""
        ticker = raw_ticker.replace(".SS", "").replace(".SZ", "").strip()
        return ticker.zfill(6)  # Ensure 6 digits

    def _yf_ticker(self, ticker: str) -> str:
        """Get yfinance-compatible ticker with exchange suffix.

        Shanghai (SSE): tickers starting with 6 → .SS
        Shenzhen (SZSE): tickers starting with 0, 3 → .SZ
        """
        if ticker.startswith("6"):
            return f"{ticker}.SS"
        else:
            return f"{ticker}.SZ"

    def get_quote(self, ticker: str) -> StockQuote:
        ticker = self.detect_ticker(ticker)
        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        price = info.get("currentPrice", info.get("regularMarketPrice", 0))
        prev_close = info.get("previousClose", price)
        change = price - prev_close if price and prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0

        return StockQuote(
            ticker=ticker,
            market=self.market_code,
            name=info.get("shortName", ticker),
            price=price,
            change=round(change, 2),
            change_pct=round(change_pct, 2),
            volume=info.get("volume", 0),
            currency="CNY",
            timestamp=datetime.now().isoformat(),
            open=info.get("open"),
            high=info.get("dayHigh"),
            low=info.get("dayLow"),
            prev_close=prev_close,
        )

    def get_price_history(self, ticker: str, start: str, end: str) -> list[PriceRecord]:
        ticker = self.detect_ticker(ticker)
        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        df = stock.history(start=start, end=end)

        records = []
        for date, row in df.iterrows():
            records.append(PriceRecord(
                date=date.strftime("%Y-%m-%d"),
                open=round(row["Open"], 4),
                high=round(row["High"], 4),
                low=round(row["Low"], 4),
                close=round(row["Close"], 4),
                volume=int(row["Volume"]),
            ))
        return records

    def get_company_info(self, ticker: str) -> CompanyInfo:
        ticker = self.detect_ticker(ticker)
        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        return CompanyInfo(
            ticker=ticker,
            market=self.market_code,
            name=info.get("shortName", ticker),
            sector=info.get("sector"),
            industry=info.get("industry"),
            description=info.get("longBusinessSummary"),
            currency="CNY",
            exchange=info.get("exchange", "SSE" if ticker.startswith("6") else "SZSE"),
            country="China",
        )

    def get_financials(self, ticker: str, period: str = "annual") -> list[dict]:
        ticker = self.detect_ticker(ticker)
        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)

        if period == "quarterly":
            income = stock.quarterly_income_stmt
            balance = stock.quarterly_balance_sheet
            cashflow = stock.quarterly_cashflow
        else:
            income = stock.income_stmt
            balance = stock.balance_sheet
            cashflow = stock.cashflow

        results = []
        for col in income.columns:
            period_date = col.strftime("%Y-%m-%d")
            record = {
                "ticker": ticker,
                "market": self.market_code,
                "period": period,
                "period_date": period_date,
            }

            record["revenue"] = _get_val(income, col, "Total Revenue")
            record["gross_profit"] = _get_val(income, col, "Gross Profit")
            record["operating_income"] = _get_val(income, col, "Operating Income")
            record["ebit"] = _get_val(income, col, "EBIT")
            record["net_income"] = _get_val(income, col, "Net Income")
            record["eps"] = _get_val(income, col, "Basic EPS")

            if col in balance.columns:
                record["total_assets"] = _get_val(balance, col, "Total Assets")
                record["total_liabilities"] = _get_val(balance, col, "Total Liabilities Net Minority Interest")
                record["total_equity"] = _get_val(balance, col, "Stockholders Equity")
                record["current_assets"] = _get_val(balance, col, "Current Assets")
                record["current_liabilities"] = _get_val(balance, col, "Current Liabilities")
                record["long_term_debt"] = _get_val(balance, col, "Long Term Debt")

                ca = record.get("current_assets")
                cl = record.get("current_liabilities")
                if ca is not None and cl is not None:
                    record["working_capital"] = ca - cl

            if col in cashflow.columns:
                record["operating_cash_flow"] = _get_val(cashflow, col, "Operating Cash Flow")
                record["capex"] = _get_val(cashflow, col, "Capital Expenditure")

                ocf = record.get("operating_cash_flow")
                capex = record.get("capex")
                if ocf is not None and capex is not None:
                    record["fcf"] = ocf + capex

            results.append(record)

        return results

    def get_key_metrics(self, ticker: str) -> dict:
        ticker = self.detect_ticker(ticker)
        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "market": self.market_code,
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "de_ratio": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "net_margin": info.get("profitMargins"),
            "dividend_yield": info.get("dividendYield"),
            "market_cap": info.get("marketCap"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }

    def list_tickers(self, sector: str = None) -> list[dict]:
        """List China A-share stocks.

        Yahoo Finance does not provide a full A-share listing endpoint.
        Returns a curated list of major stocks. For comprehensive listing,
        consider using a paid API (see prompts/_TODO.md).
        """
        return [
            {"ticker": "600519", "name": "贵州茅台"},
            {"ticker": "601318", "name": "中国平安"},
            {"ticker": "600036", "name": "招商银行"},
            {"ticker": "000858", "name": "五粮液"},
            {"ticker": "000333", "name": "美的集团"},
            {"ticker": "600900", "name": "长江电力"},
            {"ticker": "601398", "name": "工商银行"},
            {"ticker": "600276", "name": "恒瑞医药"},
            {"ticker": "000001", "name": "平安银行"},
            {"ticker": "600030", "name": "中信证券"},
            {"ticker": "300750", "name": "宁德时代"},
            {"ticker": "601012", "name": "隆基绿能"},
            {"ticker": "600809", "name": "山西汾酒"},
            {"ticker": "000568", "name": "泸州老窖"},
            {"ticker": "002594", "name": "比亚迪"},
            {"ticker": "601888", "name": "中国中免"},
            {"ticker": "600309", "name": "万华化学"},
            {"ticker": "002415", "name": "海康威视"},
            {"ticker": "600585", "name": "海螺水泥"},
            {"ticker": "601166", "name": "兴业银行"},
        ]


def _get_val(df, col, row_name):
    """Safely get a value from a DataFrame."""
    try:
        val = df.loc[row_name, col]
        if val is not None and str(val) != "nan":
            return float(val)
    except (KeyError, ValueError, TypeError):
        pass
    return None
