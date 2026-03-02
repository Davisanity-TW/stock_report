"""
Taiwan market data fetcher using twstock + yfinance fallback.

twstock provides real-time quotes and basic info for TWSE/TPEx stocks.
yfinance is used as fallback for financials (append .TW or .TWO suffix).
"""

from datetime import datetime, timedelta

import yfinance as yf

try:
    import twstock
    HAS_TWSTOCK = True
except ImportError:
    HAS_TWSTOCK = False

from fetcher_base import MarketDataFetcher, StockQuote, CompanyInfo, PriceRecord


class TWFetcher(MarketDataFetcher):
    """Taiwan market data fetcher."""

    @property
    def market_code(self) -> str:
        return "TW"

    def detect_ticker(self, raw_ticker: str) -> str:
        """Normalize Taiwan ticker (strip .TW/.TWO suffix if present)."""
        return raw_ticker.replace(".TW", "").replace(".TWO", "").strip()

    def _yf_ticker(self, ticker: str) -> str:
        """Get yfinance-compatible ticker."""
        return f"{ticker}.TW"

    def get_quote(self, ticker: str) -> StockQuote:
        ticker = self.detect_ticker(ticker)

        if HAS_TWSTOCK:
            stock = twstock.realtime.get(ticker)
            if stock["success"]:
                info = stock["realtime"]
                price = float(info["latest_trade_price"]) if info["latest_trade_price"] else 0
                open_price = float(info["open"]) if info["open"] else None
                high = float(info["high"]) if info["high"] else None
                low = float(info["low"]) if info["low"] else None
                volume = int(info["accumulate_trade_volume"]) if info["accumulate_trade_volume"] else 0
                prev_close = float(stock["realtime"].get("yesterday_close", 0)) if stock["realtime"].get("yesterday_close") else price

                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0

                return StockQuote(
                    ticker=ticker,
                    market=self.market_code,
                    name=stock["info"]["name"],
                    price=price,
                    change=round(change, 2),
                    change_pct=round(change_pct, 2),
                    volume=volume,
                    currency="TWD",
                    timestamp=datetime.now().isoformat(),
                    open=open_price,
                    high=high,
                    low=low,
                    prev_close=prev_close,
                )

        # Fallback to yfinance
        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        price = info.get("currentPrice", info.get("regularMarketPrice", 0))
        prev_close = info.get("previousClose", price)
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        return StockQuote(
            ticker=ticker,
            market=self.market_code,
            name=info.get("shortName", ticker),
            price=price,
            change=round(change, 2),
            change_pct=round(change_pct, 2),
            volume=info.get("volume", 0),
            currency="TWD",
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
                open=round(row["Open"], 2),
                high=round(row["High"], 2),
                low=round(row["Low"], 2),
                close=round(row["Close"], 2),
                volume=int(row["Volume"]),
            ))
        return records

    def get_company_info(self, ticker: str) -> CompanyInfo:
        ticker = self.detect_ticker(ticker)

        name = None
        if HAS_TWSTOCK and ticker in twstock.codes:
            code_info = twstock.codes[ticker]
            name = code_info.name

        yf_ticker = self._yf_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        return CompanyInfo(
            ticker=ticker,
            market=self.market_code,
            name=name or info.get("shortName", ticker),
            sector=info.get("sector"),
            industry=info.get("industry"),
            description=info.get("longBusinessSummary"),
            currency="TWD",
            exchange=info.get("exchange", "TWSE"),
            website=info.get("website"),
            employees=info.get("fullTimeEmployees"),
            country="Taiwan",
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
                record["retained_earnings"] = _get_val(balance, col, "Retained Earnings")

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
        """List Taiwan stocks using twstock codes database."""
        if not HAS_TWSTOCK:
            return [
                {"ticker": "2330", "name": "台積電"},
                {"ticker": "2317", "name": "鴻海"},
                {"ticker": "2454", "name": "聯發科"},
                {"ticker": "2308", "name": "台達電"},
                {"ticker": "2881", "name": "富邦金"},
            ]

        results = []
        for code, info in twstock.codes.items():
            if info.market == "上市" or info.market == "上櫃":
                results.append({
                    "ticker": code,
                    "name": info.name,
                    "market_type": info.market,
                    "industry": info.group,
                })
        return results


def _get_val(df, col, row_name):
    """Safely get a value from a DataFrame."""
    try:
        val = df.loc[row_name, col]
        if val is not None and str(val) != "nan":
            return float(val)
    except (KeyError, ValueError, TypeError):
        pass
    return None
