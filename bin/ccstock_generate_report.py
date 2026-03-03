#!/usr/bin/env python3
"""Generate CCStockWorkEnv-style markdown reports and publish into stock_report site.

This is a lightweight integration: we reuse CCStockWorkEnv's python modules
(vendored under external/ccstockworkenv/tool_scripts) and write output into
this repo's reports/ccstock folder, which is published via VitePress.

Usage examples:
  ./.venv_ccstock/bin/python bin/ccstock_generate_report.py --ticker 2330 --market TW
  ./.venv_ccstock/bin/python bin/ccstock_generate_report.py --ticker AAPL --market US

Outputs:
  reports/analysis/YYYY-Www.md (upsert daily section)
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CCROOT = ROOT / "external" / "ccstockworkenv" / "tool_scripts"

# Make CCStockWorkEnv modules importable
sys.path.insert(0, str(CCROOT / "report_gen"))
sys.path.insert(0, str(CCROOT / "market_data"))
sys.path.insert(0, str(CCROOT / "financial_calc"))

from fetcher_factory import get_fetcher  # type: ignore
from markdown_report import generate_single_report  # type: ignore


def iso_week_file(day: dt.date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}.md"


def upsert_daily_section(weekly_path: Path, day: dt.date, content_md: str) -> None:
    """Upsert section starting with `## YYYY-MM-DD` until next such header."""

    date_str = day.isoformat()
    header_prefix = f"## {date_str}"

    if not weekly_path.exists():
        weekly_path.parent.mkdir(parents=True, exist_ok=True)
        weekly_path.write_text(
            f"# CC股票研究工具（Analysis）({iso_week_file(day).replace('.md','')})\n\n",
            encoding="utf-8",
        )

    lines = weekly_path.read_text(encoding="utf-8").splitlines(True)

    def is_hdr(ln: str) -> bool:
        return ln.startswith("## ") and len(ln) >= 13 and ln[3:13].count("-") == 2

    # Find existing
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(header_prefix):
            start = i
            break

    block = content_md
    if not block.endswith("\n"):
        block += "\n"

    block_lines = block.splitlines(True)
    if not block_lines or not block_lines[0].startswith("## "):
        raise SystemExit("content must start with a '## YYYY-MM-DD ...' header")

    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("\n")
        lines.append(block)
        weekly_path.write_text("".join(lines), encoding="utf-8")
        return

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if is_hdr(lines[j]):
            end = j
            break

    # preserve existing header line, replace body
    new_section = [lines[start]] + block_lines[1:]
    if new_section and not new_section[-1].endswith("\n"):
        new_section[-1] += "\n"

    out = lines[:start] + new_section
    if end < len(lines):
        if out and out[-1].strip() != "":
            out.append("\n")
        out.extend(lines[end:])

    weekly_path.write_text("".join(out), encoding="utf-8")


def _fmt_pct(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "N/A"
    if abs(value) < 1:
        return f"{value*100:.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def _fmt_cap_twd(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value/1e8:.1f} 億"


def _fmt_vol_shares(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value/1e8:.2f} 億股"


def _demote_headings(md: str, base_level: int = 4) -> str:
    """Demote all markdown headings to at least base_level.

    Example: '# ' -> '#### ' when base_level=4.
    """

    out_lines: list[str] = []
    for ln in md.splitlines(True):
        m = re.match(r"^(#{1,6})\s+", ln)
        if not m:
            out_lines.append(ln)
            continue
        hashes = m.group(1)
        level = min(6, max(base_level, len(hashes) + (base_level - 1)))
        out_lines.append("#" * level + ln[len(hashes) :])
    return "".join(out_lines)


def _normalize_md_tables(md: str) -> str:
    """Fix common table formatting issues that break VitePress rendering.

    Currently normalizes accidental double pipes ("||") in table rows.
    Only touches lines that look like markdown table lines.
    """

    fixed: list[str] = []
    for ln in md.splitlines(True):
        if ln.lstrip().startswith("|") and "||" in ln:
            while "||" in ln:
                ln = ln.replace("||", "|")
        fixed.append(ln)
    return "".join(fixed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--market", required=True, choices=["TW", "US", "CN"])
    ap.add_argument("--name", default="", help="中文名稱（可選）。例如：群創")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today Asia/Taipei)")
    args = ap.parse_args()

    # Date based on Asia/Taipei for report filing
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Taipei")
        day = dt.datetime.now(tz).date() if not args.date else dt.date.fromisoformat(args.date)
    except Exception:
        day = dt.date.today() if not args.date else dt.date.fromisoformat(args.date)

    # Fetch minimal numbers for the ~500字摘要（用來補足可讀性）
    fetcher = get_fetcher(args.market)
    info = fetcher.get_company_info(args.ticker)
    metrics = fetcher.get_key_metrics(args.ticker)
    quote = fetcher.get_quote(args.ticker)
    financials = fetcher.get_financials(args.ticker, period="annual")

    name_zh = args.name.strip() or (getattr(info, "name", "").strip() or args.ticker)
    title = f"{day.strftime('%Y%m%d')}-{args.ticker}-{name_zh}"

    # Generate CCStockWorkEnv full markdown (contains tables)
    out_dir = ROOT / "tmp" / "ccstock"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = generate_single_report(args.ticker, args.market, str(out_dir))
    raw_md = Path(report_path).read_text(encoding="utf-8")

    # Remove the first H1 title line to avoid duplicate; keep everything else (tables included)
    raw_lines = raw_md.splitlines(True)
    if raw_lines and raw_lines[0].startswith("# "):
        raw_lines = raw_lines[1:]
    body_md = _demote_headings("".join(raw_lines), base_level=4)
    body_md = _normalize_md_tables(body_md)

    # Build ~500字摘要（預設更詳盡）
    # Note: 字數為近似值（偏 450~650 字），避免過度精算增加 token。
    s = []
    s.append(f"{name_zh}（{args.ticker}）本次報告以即時行情、關鍵指標與近年財務趨勢為主。")
    s.append(
        f"目前股價 {quote.price:.2f} 元（{quote.change:+.2f} / {quote.change_pct:+.2f}%），日內區間 {quote.low:.2f}–{quote.high:.2f}，成交量 {_fmt_vol_shares(quote.volume)}，顯示短線波動偏大。"
    )
    s.append(
        f"估值面 P/E 約 {metrics.get('pe_ratio'):.1f}、P/B 約 {metrics.get('pb_ratio'):.2f}；股利殖利率約 {_fmt_pct(metrics.get('dividend_yield'))}。"
    )
    s.append(
        f"獲利結構方面，毛利率約 {_fmt_pct(metrics.get('gross_margin'))}、營業利益率約 {_fmt_pct(metrics.get('operating_margin'))}、淨利率約 {_fmt_pct(metrics.get('net_margin'))}；在面板景氣循環下，利潤率的回升/下滑往往領先股價評價。"
    )
    s.append(
        f"財務健檢上，Z-Score 與 F-Score 可作為風險與改善動能的輔助觀察：若 F-Score 偏高，通常代表獲利/現金流/效率改善較一致；但若 Z-Score 落在灰色地帶，仍需留意資產負債結構與景氣反轉的壓力測試。"
    )
    if financials and len(financials) >= 2:
        a, b = financials[0], financials[1]
        s.append(
            f"以年度數據看，最新年度營收約 {a.get('revenue',0)/1e9:.1f}B、EPS {a.get('eps','N/A')}（前一年 {b.get('eps','N/A')}），自由現金流約 {a.get('fcf',0)/1e9:.2f}B；重點在於營收增長是否伴隨毛利與現金流同步改善，而非僅靠一次性損益。"
        )
    s.append(
        f"結論上，短線需先釐清本次劇烈波動背後的事件/籌碼與量能延續；中期則建議追蹤（1）報價與產能利用率、（2）毛利率/營益率趨勢、（3）現金流與資本支出節奏、（4）大盤風險偏好與同族群輪動。"
    )

    summary = "".join(s)

    # Wrap into daily section + per-stock subheading
    header = f"## {day.isoformat()} ({day.strftime('%a')})\n\n"
    block = (
        header
        + f"### {title}\n\n"
        + f"#### 研究摘要（預設詳盡｜約500字）\n\n{summary}\n\n"
        + body_md
    )

    weekly = ROOT / "reports" / "analysis" / iso_week_file(day)
    upsert_daily_section(weekly, day, block)

    print(str(weekly))


if __name__ == "__main__":
    main()
