#!/usr/bin/env python3
"""
Database manager for CCStockWorkEnv.
Handles schema initialization, migrations, and WAL mode.

Usage:
    python db_manager.py --init          # Initialize database with schema
    python db_manager.py --migrate       # Run pending migrations
    python db_manager.py --info          # Show database info
"""

import argparse
import os
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "ccstockworkenv.db")

CURRENT_SCHEMA_VERSION = 2

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Stock universe
CREATE TABLE IF NOT EXISTS stocks (
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,  -- US, TW, CN
    name TEXT,
    sector TEXT,
    industry TEXT,
    currency TEXT,
    exchange TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, market)
);

-- Daily OHLCV price data
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    adj_close REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, market, date),
    FOREIGN KEY (ticker, market) REFERENCES stocks(ticker, market)
);

-- Financial statements (key metrics by period)
CREATE TABLE IF NOT EXISTS financials (
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    period TEXT NOT NULL,       -- 'annual' or 'quarterly'
    period_date TEXT NOT NULL,  -- e.g., '2025-12-31'
    -- Income statement
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    ebit REAL,
    net_income REAL,
    eps REAL,
    -- Balance sheet
    total_assets REAL,
    total_liabilities REAL,
    total_equity REAL,
    current_assets REAL,
    current_liabilities REAL,
    long_term_debt REAL,
    retained_earnings REAL,
    working_capital REAL,
    -- Cash flow
    operating_cash_flow REAL,
    capex REAL,
    fcf REAL,
    -- Market data
    market_cap REAL,
    shares_outstanding REAL,
    -- Computed ratios
    pe_ratio REAL,
    pb_ratio REAL,
    roe REAL,
    roa REAL,
    de_ratio REAL,
    current_ratio REAL,
    gross_margin REAL,
    operating_margin REAL,
    net_margin REAL,
    asset_turnover REAL,
    dividend_yield REAL,
    fcf_yield REAL,
    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, market, period, period_date),
    FOREIGN KEY (ticker, market) REFERENCES stocks(ticker, market)
);

-- Saved screening results
CREATE TABLE IF NOT EXISTS screening_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL DEFAULT (datetime('now')),
    market TEXT,
    criteria_json TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    results_json TEXT NOT NULL,  -- JSON array of matching tickers + scores
    notes TEXT
);

-- Watchlist with notes and alerts
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    added_date TEXT NOT NULL DEFAULT (datetime('now')),
    target_price REAL,
    stop_loss REAL,
    notes TEXT,
    tags TEXT,  -- comma-separated tags
    is_active INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (ticker, market),
    FOREIGN KEY (ticker, market) REFERENCES stocks(ticker, market)
);

-- Cached health scores — tied to financial reporting periods
CREATE TABLE IF NOT EXISTS health_scores (
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    period TEXT NOT NULL,           -- 'annual' or 'quarterly' (matches financials)
    period_date TEXT NOT NULL,      -- e.g., '2025-12-31' (matches financials)
    -- Solvency & Risk
    zscore REAL,
    zscore_zone TEXT,               -- 'safe', 'grey', 'distress'
    quick_ratio REAL,
    interest_coverage REAL,
    -- Quality (Piotroski F-Score breakdown)
    fscore INTEGER,                 -- 0-9 total
    fscore_details_json TEXT,       -- JSON breakdown of 9 criteria
    -- Cash Flow Quality
    ocf_to_net_income REAL,         -- Operating CF / Net Income (>1.0 = quality earnings)
    -- Growth (YoY vs previous period)
    revenue_growth REAL,            -- YoY revenue growth %
    net_income_growth REAL,         -- YoY net income growth %
    eps_growth REAL,                -- YoY EPS growth %
    -- Composite
    opportunity_score REAL,
    opportunity_details_json TEXT,
    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, market, period, period_date),
    FOREIGN KEY (ticker, market, period, period_date)
        REFERENCES financials(ticker, market, period, period_date)
);

-- Research cache — tracks when data was last fetched from APIs
CREATE TABLE IF NOT EXISTS research_cache (
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    data_type TEXT NOT NULL,        -- 'financials', 'metrics', 'company_info'
    last_fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    data_json TEXT,                 -- JSON for metrics & company_info
    fetch_source TEXT,              -- 'yfinance', 'twstock', etc.
    PRIMARY KEY (ticker, market, data_type)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_daily_prices_market ON daily_prices(market);
CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(date);
CREATE INDEX IF NOT EXISTS idx_stocks_market ON stocks(market);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_financials_market ON financials(market);
CREATE INDEX IF NOT EXISTS idx_health_scores_period ON health_scores(period, period_date);
CREATE INDEX IF NOT EXISTS idx_research_cache_type ON research_cache(data_type);
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Get a database connection with WAL mode enabled."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize database with full schema."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    # Record schema version
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
        (CURRENT_SCHEMA_VERSION,),
    )
    conn.commit()
    conn.close()
    print(f"Database initialized at: {db_path}")
    print(f"Schema version: {CURRENT_SCHEMA_VERSION}")


def get_schema_version(db_path: str = DB_PATH) -> int:
    """Get current schema version."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] if row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def migrate(db_path: str = DB_PATH) -> None:
    """Run pending migrations."""
    current = get_schema_version(db_path)
    if current >= CURRENT_SCHEMA_VERSION:
        print(f"Database is up to date (version {current})")
        return

    print(f"Migrating from version {current} to {CURRENT_SCHEMA_VERSION}...")
    conn = get_connection(db_path)

    if current < 2:
        print("  Applying migration v1 → v2: research cache + health_scores redesign...")

        # 1. Add new columns to financials
        new_columns = [
            ("quick_ratio", "REAL"),
            ("interest_coverage", "REAL"),
            ("ps_ratio", "REAL"),
            ("ev_ebitda", "REAL"),
            ("payout_ratio", "REAL"),
            ("cash_and_equivalents", "REAL"),
            ("total_debt", "REAL"),
            ("ebitda", "REAL"),
            ("inventory", "REAL"),
            ("receivables", "REAL"),
            ("inventory_turnover_days", "REAL"),
            ("receivable_turnover_days", "REAL"),
        ]
        existing = {row[1] for row in conn.execute("PRAGMA table_info(financials)").fetchall()}
        for col_name, col_type in new_columns:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE financials ADD COLUMN {col_name} {col_type}")
                print(f"    Added financials.{col_name}")

        # 2. Drop old health_scores (0 rows, safe) and recreate with new PK
        conn.execute("DROP TABLE IF EXISTS health_scores")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS health_scores (
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                period TEXT NOT NULL,
                period_date TEXT NOT NULL,
                zscore REAL,
                zscore_zone TEXT,
                quick_ratio REAL,
                interest_coverage REAL,
                fscore INTEGER,
                fscore_details_json TEXT,
                ocf_to_net_income REAL,
                revenue_growth REAL,
                net_income_growth REAL,
                eps_growth REAL,
                opportunity_score REAL,
                opportunity_details_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (ticker, market, period, period_date),
                FOREIGN KEY (ticker, market, period, period_date)
                    REFERENCES financials(ticker, market, period, period_date)
            );
            CREATE INDEX IF NOT EXISTS idx_health_scores_period ON health_scores(period, period_date);
        """)
        print("    Recreated health_scores with new PK (ticker, market, period, period_date)")

        # 3. Create research_cache table
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS research_cache (
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                data_type TEXT NOT NULL,
                last_fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                data_json TEXT,
                fetch_source TEXT,
                PRIMARY KEY (ticker, market, data_type)
            );
            CREATE INDEX IF NOT EXISTS idx_research_cache_type ON research_cache(data_type);
        """)
        print("    Created research_cache table")

        # 4. Drop old index if exists
        conn.execute("DROP INDEX IF EXISTS idx_health_scores_date")

        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.commit()
        print("  Migration v1 → v2 complete")

    conn.close()
    print(f"Migration complete (now at version {CURRENT_SCHEMA_VERSION})")


def show_info(db_path: str = DB_PATH) -> None:
    """Show database information."""
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("Run --init to create it.")
        return

    conn = get_connection(db_path)
    version = get_schema_version(db_path)
    size_mb = os.path.getsize(db_path) / (1024 * 1024)

    print(f"Database: {db_path}")
    print(f"Size: {size_mb:.2f} MB")
    print(f"Schema version: {version}")
    print()

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    print("Tables:")
    for table in tables:
        name = table["name"]
        count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"  {name}: {count} rows")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="CCStockWorkEnv database manager")
    parser.add_argument("--init", action="store_true", help="Initialize database with schema")
    parser.add_argument("--migrate", action="store_true", help="Run pending migrations")
    parser.add_argument("--info", action="store_true", help="Show database info")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Database path")

    args = parser.parse_args()

    if args.init:
        init_db(args.db)
    elif args.migrate:
        migrate(args.db)
    elif args.info:
        show_info(args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
