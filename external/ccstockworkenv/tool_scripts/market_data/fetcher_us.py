"""
US market data fetcher using yfinance.
"""

from datetime import datetime

import yfinance as yf

from fetcher_base import MarketDataFetcher, StockQuote, CompanyInfo, PriceRecord


class USFetcher(MarketDataFetcher):
    """US market data fetcher using yfinance (free, no API key)."""

    @property
    def market_code(self) -> str:
        return "US"

    def get_quote(self, ticker: str) -> StockQuote:
        ticker = self.detect_ticker(ticker)
        stock = yf.Ticker(ticker)
        info = stock.info

        price = info["currentPrice"]
        prev_close = info["previousClose"]
        change = price - prev_close
        change_pct = (change / prev_close) * 100

        return StockQuote(
            ticker=ticker,
            market=self.market_code,
            name=info.get("shortName", ticker),
            price=price,
            change=round(change, 2),
            change_pct=round(change_pct, 2),
            volume=info.get("volume", 0),
            currency=info.get("currency", "USD"),
            timestamp=datetime.now().isoformat(),
            open=info.get("open"),
            high=info.get("dayHigh"),
            low=info.get("dayLow"),
            prev_close=prev_close,
        )

    def get_price_history(self, ticker: str, start: str, end: str) -> list[PriceRecord]:
        ticker = self.detect_ticker(ticker)
        stock = yf.Ticker(ticker)
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
        stock = yf.Ticker(ticker)
        info = stock.info

        return CompanyInfo(
            ticker=ticker,
            market=self.market_code,
            name=info.get("shortName", ticker),
            sector=info.get("sector"),
            industry=info.get("industry"),
            description=info.get("longBusinessSummary"),
            currency=info.get("currency", "USD"),
            exchange=info.get("exchange"),
            website=info.get("website"),
            employees=info.get("fullTimeEmployees"),
            country=info.get("country"),
        )

    def get_financials(self, ticker: str, period: str = "annual") -> list[dict]:
        ticker = self.detect_ticker(ticker)
        stock = yf.Ticker(ticker)

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

            # Income statement
            record["revenue"] = _get_val(income, col, "Total Revenue")
            record["gross_profit"] = _get_val(income, col, "Gross Profit")
            record["operating_income"] = _get_val(income, col, "Operating Income")
            record["ebit"] = _get_val(income, col, "EBIT")
            record["net_income"] = _get_val(income, col, "Net Income")
            record["eps"] = _get_val(income, col, "Basic EPS")

            # Balance sheet
            if col in balance.columns:
                record["total_assets"] = _get_val(balance, col, "Total Assets")
                record["total_liabilities"] = _get_val(balance, col, "Total Liabilities Net Minority Interest")
                record["total_equity"] = _get_val(balance, col, "Stockholders Equity")
                record["current_assets"] = _get_val(balance, col, "Current Assets")
                record["current_liabilities"] = _get_val(balance, col, "Current Liabilities")
                record["long_term_debt"] = _get_val(balance, col, "Long Term Debt")
                record["retained_earnings"] = _get_val(balance, col, "Retained Earnings")

                ca = record["current_assets"]
                cl = record["current_liabilities"]
                if ca is not None and cl is not None:
                    record["working_capital"] = ca - cl

            # Cash flow
            if col in cashflow.columns:
                record["operating_cash_flow"] = _get_val(cashflow, col, "Operating Cash Flow")
                record["capex"] = _get_val(cashflow, col, "Capital Expenditure")

                ocf = record["operating_cash_flow"]
                capex = record["capex"]
                if ocf is not None and capex is not None:
                    record["fcf"] = ocf + capex  # capex is negative

            results.append(record)

        return results

    def get_key_metrics(self, ticker: str) -> dict:
        ticker = self.detect_ticker(ticker)
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "market": self.market_code,
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "peg_ratio": info.get("pegRatio"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "de_ratio": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "net_margin": info.get("profitMargins"),
            "dividend_yield": info.get("dividendYield"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "beta": info.get("beta"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
        }

    def list_tickers(self, sector: str = None) -> list[dict]:
        """List major US tickers. For full universe, use a database or screening API."""
        # yfinance doesn't have a built-in ticker listing.
        # Return a curated list of major indices components.
        # For production use, download from exchanges or use a screening service.
        major_tickers = [
            {"ticker": "AAPL", "name": "Apple Inc"},
            {"ticker": "MSFT", "name": "Microsoft Corporation"},
            {"ticker": "GOOGL", "name": "Alphabet Inc"},
            {"ticker": "AMZN", "name": "Amazon.com Inc"},
            {"ticker": "NVDA", "name": "NVIDIA Corporation"},
            {"ticker": "META", "name": "Meta Platforms Inc"},
            {"ticker": "TSLA", "name": "Tesla Inc"},
            {"ticker": "BRK-B", "name": "Berkshire Hathaway Inc"},
            {"ticker": "JPM", "name": "JPMorgan Chase & Co"},
            {"ticker": "V", "name": "Visa Inc"},
        ]
        return major_tickers


def _get_val(df, col, row_name):
    """Safely get a value from a DataFrame, return None if not found."""
    try:
        val = df.loc[row_name, col]
        if val is not None and str(val) != "nan":
            return float(val)
    except (KeyError, ValueError, TypeError):
        pass
    return None
