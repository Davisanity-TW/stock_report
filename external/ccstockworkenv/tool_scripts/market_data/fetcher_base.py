"""
Abstract base class for market data fetchers.

All market-specific fetchers must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StockQuote:
    """Current stock quote."""
    ticker: str
    market: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    currency: str
    timestamp: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None


@dataclass
class CompanyInfo:
    """Company profile information."""
    ticker: str
    market: str
    name: str
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    currency: str | None = None
    exchange: str | None = None
    website: str | None = None
    employees: int | None = None
    country: str | None = None


@dataclass
class PriceRecord:
    """Single day price record."""
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    adj_close: float | None = None


class MarketDataFetcher(ABC):
    """Abstract base class for market data fetchers."""

    @property
    @abstractmethod
    def market_code(self) -> str:
        """Return the market code (US, TW, CN)."""
        ...

    @abstractmethod
    def get_quote(self, ticker: str) -> StockQuote:
        """Get current stock quote."""
        ...

    @abstractmethod
    def get_price_history(self, ticker: str, start: str, end: str) -> list[PriceRecord]:
        """Get historical price data.

        Args:
            ticker: Stock ticker symbol
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)

        Returns:
            List of PriceRecord sorted by date ascending
        """
        ...

    @abstractmethod
    def get_company_info(self, ticker: str) -> CompanyInfo:
        """Get company profile information."""
        ...

    @abstractmethod
    def get_financials(self, ticker: str, period: str = "annual") -> list[dict]:
        """Get financial statements.

        Args:
            ticker: Stock ticker symbol
            period: 'annual' or 'quarterly'

        Returns:
            List of dicts with financial data, most recent first
        """
        ...

    @abstractmethod
    def get_key_metrics(self, ticker: str) -> dict:
        """Get key financial metrics (P/E, P/B, ROE, etc.)."""
        ...

    @abstractmethod
    def list_tickers(self, sector: str = None) -> list[dict]:
        """List available tickers, optionally filtered by sector.

        Returns:
            List of dicts with at least 'ticker' and 'name' keys
        """
        ...

    def detect_ticker(self, raw_ticker: str) -> str:
        """Normalize ticker format for this market. Override if needed."""
        return raw_ticker.upper()
