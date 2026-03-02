#!/usr/bin/env python3
"""
Generate the China A-share 3-year low research report.

Reads health check results and generates markdown + HTML reports in 繁體中文.

Usage:
    python cn_3yr_low_report.py                  # Generate both .md and .html
    python cn_3yr_low_report.py --format md       # Markdown only
    python cn_3yr_low_report.py --format html     # HTML only (for email)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from html import escape as h

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
RESULTS_PATH = os.path.join(PROJECT_ROOT, "tool_scripts", "financial_calc", "_health_check_results.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def _fmt(val, pct=False, decimals=2):
    if val is None:
        return "N/A"
    if pct:
        if abs(val) < 1:
            return f"{val*100:.{decimals}f}%"
        return f"{val:.{decimals}f}%"
    if isinstance(val, float):
        if abs(val) >= 1e9:
            return f"{val/1e9:.1f}B"
        if abs(val) >= 1e6:
            return f"{val/1e6:.0f}M"
        return f"{val:.{decimals}f}"
    return str(val)


def _zone_zh(zone):
    return {"safe": "安全區", "grey": "灰色地帶", "distress": "危險區"}.get(zone, zone or "N/A")


def _strength_zh(s):
    return {"strong": "強健", "average": "普通", "weak": "疲弱"}.get(s, s or "N/A")


def generate_report():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    strong = [r for r in results if r.get("classification") == "STRONG"]
    passed = [r for r in results if r.get("classification") == "PASS"]
    watch = [r for r in results if r.get("classification") == "WATCH"]
    excluded = [r for r in results if r.get("classification") == "EXCLUDE"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_scanned = 128  # from our ticker list

    report = f"""# 中國A股三年低點研究報告

> 產生時間：{timestamp}
> 篩選標準：現價 ≤ 60% × 三年最高價
> 資料來源：yfinance（Yahoo Finance）
> 健康檢查：Altman Z-Score + Piotroski F-Score + 價值陷阱檢測

---

## 篩選摘要

| 項目 | 數量 |
|------|------|
| 掃描股票數 | {total_scanned} 檔（主要指數成分股） |
| 處於三年低點（≤60%） | {len(results)} 檔 |
| ⭐ 強力機會（STRONG） | {len(strong)} 檔 |
| ✅ 合格機會（PASS） | {len(passed)} 檔 |
| ⚠️ 需觀察（WATCH） | {len(watch)} 檔 |
| ❌ 排除（EXCLUDE） | {len(excluded)} 檔 |

**STRONG 條件**：Z-Score > 2.99 + F-Score ≥ 7 + ROE > 10% + D/E < 100 + 無價值陷阱
**PASS 條件**：Z-Score > 1.81 + F-Score ≥ 4 + 流動比率 > 1.0 + 無重大價值陷阱

---

## ⭐ 強力機會（STRONG）

"""

    if strong:
        report += "| # | 代號 | 名稱 | 現價 | 三年高點 | 跌幅 | Z-Score | F-Score | ROE | P/E | D/E | 殖利率 |\n"
        report += "|---|------|------|------|----------|------|---------|---------|-----|-----|-----|--------|\n"
        for i, r in enumerate(strong, 1):
            drop = f"-{100 - r['pct_of_high']:.0f}%"
            report += (
                f"| {i} | {r['ticker']} | {r['name']} | {r['current_price']:.2f} | "
                f"{r['three_year_high']:.2f} | {drop} | {_fmt(r.get('zscore'))} | "
                f"{r.get('fscore', 'N/A')}/9 | {_fmt(r.get('roe'), pct=True)} | "
                f"{_fmt(r.get('pe_ratio'))} | {_fmt(r.get('de_ratio'))} | "
                f"{_fmt(r.get('dividend_yield'), pct=True)} |\n"
            )

        report += "\n"
        for r in strong:
            report += f"""### {r['ticker']} — {r['name']}

- **現價**：¥{r['current_price']:.2f}（三年高點 ¥{r['three_year_high']:.2f} 的 {r['pct_of_high']}%）
- **三年低點**：¥{r['three_year_low']:.2f}
- **市值**：{_fmt(r.get('market_cap'))}

**健康指標：**
| 指標 | 數值 | 判定 |
|------|------|------|
| Altman Z-Score | {_fmt(r.get('zscore'))} | {_zone_zh(r.get('zscore_zone'))} |
| Piotroski F-Score | {r.get('fscore', 'N/A')}/9 | {_strength_zh(r.get('fscore_strength'))} |
| ROE | {_fmt(r.get('roe'), pct=True)} | {'良好' if r.get('roe') and r['roe'] > 0.15 else '尚可'} |
| ROA | {_fmt(r.get('roa'), pct=True)} | - |
| P/E | {_fmt(r.get('pe_ratio'))} | {'偏低' if r.get('pe_ratio') and r['pe_ratio'] < 15 else '合理' if r.get('pe_ratio') and r['pe_ratio'] < 25 else '偏高'} |
| P/B | {_fmt(r.get('pb_ratio'))} | - |
| D/E | {_fmt(r.get('de_ratio'))} | {'低負債' if r.get('de_ratio') and r['de_ratio'] < 50 else '中等'} |
| 毛利率 | {_fmt(r.get('gross_margin'), pct=True)} | - |
| 淨利率 | {_fmt(r.get('net_margin'), pct=True)} | - |
| 殖利率 | {_fmt(r.get('dividend_yield'), pct=True)} | - |

**價值陷阱檢測**：✅ 未發現價值陷阱

"""

    report += """---

## ✅ 合格機會（PASS）

| # | 代號 | 名稱 | 現價 | 三年高點 | 跌幅 | Z-Score (區) | F-Score | ROE | P/E | 價值陷阱 |
|---|------|------|------|----------|------|-------------|---------|-----|-----|----------|
"""
    for i, r in enumerate(passed, 1):
        drop = f"-{100 - r['pct_of_high']:.0f}%"
        traps = ", ".join(r.get("value_traps", [])) or "無"
        report += (
            f"| {i} | {r['ticker']} | {r['name']} | {r['current_price']:.2f} | "
            f"{r['three_year_high']:.2f} | {drop} | {_fmt(r.get('zscore'))} ({_zone_zh(r.get('zscore_zone'))}) | "
            f"{r.get('fscore', 'N/A')}/9 | {_fmt(r.get('roe'), pct=True)} | "
            f"{_fmt(r.get('pe_ratio'))} | {traps} |\n"
        )

    if excluded:
        report += f"""
---

## ❌ 排除清單（{len(excluded)} 檔）

以下股票雖處於三年低點，但因財務健康不佳或存在價值陷阱而被排除：

| # | 代號 | 名稱 | 跌幅 | Z-Score | F-Score | 排除原因 |
|---|------|------|------|---------|---------|----------|
"""
        for i, r in enumerate(excluded, 1):
            drop = f"-{100 - r['pct_of_high']:.0f}%"
            reason_str = _exclude_reasons(r)
            report += (
                f"| {i} | {r['ticker']} | {r['name']} | {drop} | "
                f"{_fmt(r.get('zscore'))} | {r.get('fscore', 'N/A')}/9 | {reason_str} |\n"
            )

    report += f"""
---

## 產業分佈分析

"""
    # Sector analysis from passed + strong stocks
    all_passed = strong + passed
    sectors = {}
    for r in all_passed:
        # Group by general category based on name
        name = r["name"]
        if any(w in name for w in ["酒", "酿"]):
            sector = "白酒"
        elif any(w in name for w in ["食品", "味", "啤酒", "飘飘", "洽洽"]):
            sector = "食品飲料"
        elif any(w in name for w in ["医", "药", "堂", "眼科"]):
            sector = "醫藥健康"
        elif any(w in name for w in ["科技", "软件", "办公", "网络", "创达"]):
            sector = "科技軟體"
        elif any(w in name for w in ["免税", "机场", "航空"]):
            sector = "消費/旅遊"
        elif any(w in name for w in ["能源", "光能", "科技"]):
            sector = "新能源"
        elif any(w in name for w in ["证券", "金融"]):
            sector = "金融"
        else:
            sector = "其他"
        sectors.setdefault(sector, []).append(r)

    report += "| 產業 | 數量 | 代表個股 |\n"
    report += "|------|------|----------|\n"
    for sector, stocks in sorted(sectors.items(), key=lambda x: -len(x[1])):
        names = ", ".join(f"{s['name']}({s['ticker']})" for s in stocks[:3])
        report += f"| {sector} | {len(stocks)} | {names} |\n"

    report += f"""
---

## 研究限制

1. **股票覆蓋範圍**：本次分析涵蓋 128 檔主要指數成分股，非全市場 5,000+ 檔 A 股。如需完整市場掃描，需從中國大陸網絡環境使用 AKShare API。
2. **資料來源**：使用 Yahoo Finance (yfinance) 作為數據來源，部分 A 股的財務數據可能不完整。
3. **時間點**：數據截止至 {datetime.now().strftime('%Y-%m-%d')}，股價隨時變動。
4. **產業分類**：基於簡易名稱判斷，非正式產業分類標準。

---

## 免責聲明

本報告僅供研究參考，不構成投資建議。投資有風險，入市需謹慎。所有分析基於歷史數據和公開信息，不保證未來表現。請在做出任何投資決策前，進行自己的盡職調查。

---

*報告由 CCStockWorkEnv 自動產生 — {timestamp}*
"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_cn_3yr_low_research.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report saved: {filepath}")
    print(f"Sections: STRONG({len(strong)}), PASS({len(passed)}), WATCH({len(watch)}), EXCLUDE({len(excluded)})")
    return filepath


def _exclude_reasons(r):
    """Build exclude reason list for a stock."""
    reasons = []
    z = r.get("zscore")
    f_s = r.get("fscore")
    if z is not None and z <= 1.81:
        reasons.append(f"Z-Score {z:.2f} (危險區)")
    if f_s is not None and f_s < 4:
        reasons.append(f"F-Score {f_s}/9 (疲弱)")
    for t in r.get("value_traps", []):
        if "revenue" in t:
            reasons.append("營收衰退")
        elif "fcf" in t:
            reasons.append("FCF連虧")
        elif "debt" in t:
            reasons.append("負債攀升")
        elif "net_loss" in t:
            reasons.append("淨虧損")
    return "; ".join(reasons) or "未通過基本條件"


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; max-width: 800px; margin: 0 auto; padding: 20px; background: #f8f9fa; }
h1 { color: #c0392b; border-bottom: 3px solid #c0392b; padding-bottom: 8px; }
h2 { color: #2c3e50; margin-top: 32px; }
h3 { color: #34495e; }
.meta { color: #666; font-size: 0.9em; line-height: 1.6; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.85em; }
th { background: #2c3e50; color: #fff; padding: 8px 10px; text-align: left; }
td { padding: 7px 10px; border-bottom: 1px solid #ddd; }
tr:nth-child(even) { background: #f2f2f2; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
.badge-strong { background: #27ae60; color: #fff; }
.badge-pass { background: #2980b9; color: #fff; }
.badge-watch { background: #f39c12; color: #fff; }
.badge-exclude { background: #c0392b; color: #fff; }
.zone-safe { color: #27ae60; font-weight: bold; }
.zone-grey { color: #f39c12; font-weight: bold; }
.zone-distress { color: #c0392b; font-weight: bold; }
.card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; }
.card h3 { margin-top: 0; }
.metric-good { color: #27ae60; }
.metric-ok { color: #f39c12; }
.metric-bad { color: #c0392b; }
.disclaimer { color: #999; font-size: 0.8em; margin-top: 32px; padding-top: 16px; border-top: 1px solid #ddd; }
.footer { text-align: center; color: #aaa; font-size: 0.8em; margin-top: 24px; }
"""


def _zone_class(zone):
    return {"safe": "zone-safe", "grey": "zone-grey", "distress": "zone-distress"}.get(zone, "")


def _zone_color(zone):
    """Inline color for email clients that strip <style>."""
    return {"safe": "#27ae60", "grey": "#f39c12", "distress": "#c0392b"}.get(zone, "#666")


def generate_html_report():
    """Generate an email-safe HTML report."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    strong = [r for r in results if r.get("classification") == "STRONG"]
    passed = [r for r in results if r.get("classification") == "PASS"]
    watch = [r for r in results if r.get("classification") == "WATCH"]
    excluded = [r for r in results if r.get("classification") == "EXCLUDE"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_scanned = 128

    # --- Build HTML ---
    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
<h1>中國A股三年低點研究報告</h1>
<div class="meta">
產生時間：{timestamp}<br>
篩選標準：現價 ≤ 60% × 三年最高價<br>
資料來源：yfinance（Yahoo Finance）<br>
健康檢查：Altman Z-Score + Piotroski F-Score + 價值陷阱檢測
</div>

<h2>篩選摘要</h2>
<table>
<tr><th>項目</th><th>數量</th></tr>
<tr><td>掃描股票數</td><td>{total_scanned} 檔（主要指數成分股）</td></tr>
<tr><td>處於三年低點（≤60%）</td><td>{len(results)} 檔</td></tr>
<tr><td><span style="color:#27ae60;font-weight:bold">⭐ 強力機會（STRONG）</span></td><td>{len(strong)} 檔</td></tr>
<tr><td><span style="color:#2980b9;font-weight:bold">✅ 合格機會（PASS）</span></td><td>{len(passed)} 檔</td></tr>
<tr><td><span style="color:#f39c12;font-weight:bold">⚠️ 需觀察（WATCH）</span></td><td>{len(watch)} 檔</td></tr>
<tr><td><span style="color:#c0392b;font-weight:bold">❌ 排除（EXCLUDE）</span></td><td>{len(excluded)} 檔</td></tr>
</table>
<p style="font-size:0.85em;color:#555;">
<b>STRONG</b>：Z-Score &gt; 2.99 + F-Score ≥ 7 + ROE &gt; 10% + D/E &lt; 100 + 無價值陷阱<br>
<b>PASS</b>：Z-Score &gt; 1.81 + F-Score ≥ 4 + 流動比率 &gt; 1.0 + 無重大價值陷阱
</p>
""")

    # --- STRONG section ---
    if strong:
        parts.append('<h2 style="color:#27ae60">⭐ 強力機會（STRONG）</h2>')
        parts.append("""<table>
<tr><th>#</th><th>代號</th><th>名稱</th><th>現價</th><th>三年高點</th><th>跌幅</th>
<th>Z-Score</th><th>F-Score</th><th>ROE</th><th>P/E</th><th>D/E</th><th>殖利率</th></tr>""")
        for i, r in enumerate(strong, 1):
            drop = f"-{100 - r['pct_of_high']:.0f}%"
            zc = _zone_color(r.get("zscore_zone"))
            parts.append(
                f'<tr><td>{i}</td><td><b>{h(r["ticker"])}</b></td><td>{h(r["name"])}</td>'
                f'<td>{r["current_price"]:.2f}</td><td>{r["three_year_high"]:.2f}</td>'
                f'<td style="color:#c0392b;font-weight:bold">{drop}</td>'
                f'<td style="color:{zc};font-weight:bold">{_fmt(r.get("zscore"))}</td>'
                f'<td>{r.get("fscore", "N/A")}/9</td>'
                f'<td>{_fmt(r.get("roe"), pct=True)}</td>'
                f'<td>{_fmt(r.get("pe_ratio"))}</td>'
                f'<td>{_fmt(r.get("de_ratio"))}</td>'
                f'<td>{_fmt(r.get("dividend_yield"), pct=True)}</td></tr>'
            )
        parts.append("</table>")

        # Detail cards for each STRONG stock
        for r in strong:
            pe = r.get("pe_ratio")
            pe_label = "偏低" if pe and pe < 15 else ("合理" if pe and pe < 25 else "偏高")
            pe_color = "#27ae60" if pe and pe < 15 else ("#f39c12" if pe and pe < 25 else "#c0392b")
            roe_label = "良好" if r.get("roe") and r["roe"] > 0.15 else "尚可"
            de_label = "低負債" if r.get("de_ratio") and r["de_ratio"] < 50 else "中等"
            zc = _zone_color(r.get("zscore_zone"))

            parts.append(f"""<div class="card">
<h3>{h(r["ticker"])} — {h(r["name"])}</h3>
<p>
<b>現價</b>：¥{r["current_price"]:.2f}（三年高點 ¥{r["three_year_high"]:.2f} 的 {r["pct_of_high"]}%）<br>
<b>三年低點</b>：¥{r["three_year_low"]:.2f}<br>
<b>市值</b>：{_fmt(r.get("market_cap"))}
</p>
<table>
<tr><th>指標</th><th>數值</th><th>判定</th></tr>
<tr><td>Altman Z-Score</td><td style="color:{zc};font-weight:bold">{_fmt(r.get("zscore"))}</td><td>{_zone_zh(r.get("zscore_zone"))}</td></tr>
<tr><td>Piotroski F-Score</td><td><b>{r.get("fscore", "N/A")}/9</b></td><td>{_strength_zh(r.get("fscore_strength"))}</td></tr>
<tr><td>ROE</td><td>{_fmt(r.get("roe"), pct=True)}</td><td>{roe_label}</td></tr>
<tr><td>ROA</td><td>{_fmt(r.get("roa"), pct=True)}</td><td>-</td></tr>
<tr><td>P/E</td><td style="color:{pe_color}">{_fmt(r.get("pe_ratio"))}</td><td>{pe_label}</td></tr>
<tr><td>P/B</td><td>{_fmt(r.get("pb_ratio"))}</td><td>-</td></tr>
<tr><td>D/E</td><td>{_fmt(r.get("de_ratio"))}</td><td>{de_label}</td></tr>
<tr><td>毛利率</td><td>{_fmt(r.get("gross_margin"), pct=True)}</td><td>-</td></tr>
<tr><td>淨利率</td><td>{_fmt(r.get("net_margin"), pct=True)}</td><td>-</td></tr>
<tr><td>殖利率</td><td>{_fmt(r.get("dividend_yield"), pct=True)}</td><td>-</td></tr>
</table>
<p style="color:#27ae60"><b>價值陷阱檢測</b>：✅ 未發現價值陷阱</p>
</div>""")

    # --- PASS section ---
    parts.append('<h2 style="color:#2980b9">✅ 合格機會（PASS）</h2>')
    parts.append("""<table>
<tr><th>#</th><th>代號</th><th>名稱</th><th>現價</th><th>三年高點</th><th>跌幅</th>
<th>Z-Score (區)</th><th>F-Score</th><th>ROE</th><th>P/E</th><th>價值陷阱</th></tr>""")
    for i, r in enumerate(passed, 1):
        drop = f"-{100 - r['pct_of_high']:.0f}%"
        traps = ", ".join(r.get("value_traps", [])) or "無"
        zc = _zone_color(r.get("zscore_zone"))
        trap_style = ' style="color:#c0392b"' if traps != "無" else ""
        parts.append(
            f'<tr><td>{i}</td><td><b>{h(r["ticker"])}</b></td><td>{h(r["name"])}</td>'
            f'<td>{r["current_price"]:.2f}</td><td>{r["three_year_high"]:.2f}</td>'
            f'<td style="color:#c0392b">{drop}</td>'
            f'<td style="color:{zc}">{_fmt(r.get("zscore"))} ({_zone_zh(r.get("zscore_zone"))})</td>'
            f'<td>{r.get("fscore", "N/A")}/9</td>'
            f'<td>{_fmt(r.get("roe"), pct=True)}</td>'
            f'<td>{_fmt(r.get("pe_ratio"))}</td>'
            f'<td{trap_style}>{h(traps)}</td></tr>'
        )
    parts.append("</table>")

    # --- EXCLUDE section ---
    if excluded:
        parts.append(f'<h2 style="color:#c0392b">❌ 排除清單（{len(excluded)} 檔）</h2>')
        parts.append("<p>以下股票雖處於三年低點，但因財務健康不佳或存在價值陷阱而被排除：</p>")
        parts.append("""<table>
<tr><th>#</th><th>代號</th><th>名稱</th><th>跌幅</th><th>Z-Score</th><th>F-Score</th><th>排除原因</th></tr>""")
        for i, r in enumerate(excluded, 1):
            drop = f"-{100 - r['pct_of_high']:.0f}%"
            reason_str = _exclude_reasons(r)
            parts.append(
                f'<tr><td>{i}</td><td>{h(r["ticker"])}</td><td>{h(r["name"])}</td>'
                f'<td>{drop}</td><td>{_fmt(r.get("zscore"))}</td>'
                f'<td>{r.get("fscore", "N/A")}/9</td>'
                f'<td style="color:#c0392b;font-size:0.85em">{h(reason_str)}</td></tr>'
            )
        parts.append("</table>")

    # --- Sector analysis (reuse logic from markdown) ---
    all_passed = strong + passed
    sectors = {}
    for r in all_passed:
        name = r["name"]
        if any(w in name for w in ["酒", "酿"]):
            sector = "白酒"
        elif any(w in name for w in ["食品", "味", "啤酒", "飘飘", "洽洽"]):
            sector = "食品飲料"
        elif any(w in name for w in ["医", "药", "堂", "眼科"]):
            sector = "醫藥健康"
        elif any(w in name for w in ["科技", "软件", "办公", "网络", "创达"]):
            sector = "科技軟體"
        elif any(w in name for w in ["免税", "机场", "航空"]):
            sector = "消費/旅遊"
        elif any(w in name for w in ["能源", "光能"]):
            sector = "新能源"
        elif any(w in name for w in ["证券", "金融"]):
            sector = "金融"
        else:
            sector = "其他"
        sectors.setdefault(sector, []).append(r)

    parts.append("<h2>產業分佈分析</h2>")
    parts.append("<table><tr><th>產業</th><th>數量</th><th>代表個股</th></tr>")
    for sector, stocks in sorted(sectors.items(), key=lambda x: -len(x[1])):
        names = ", ".join(f"{s['name']}({s['ticker']})" for s in stocks[:3])
        parts.append(f"<tr><td>{h(sector)}</td><td>{len(stocks)}</td><td>{h(names)}</td></tr>")
    parts.append("</table>")

    # --- Limitations + Disclaimer ---
    parts.append(f"""
<h2>研究限制</h2>
<ol style="font-size:0.9em;color:#555;">
<li><b>股票覆蓋範圍</b>：本次分析涵蓋 128 檔主要指數成分股，非全市場 5,000+ 檔 A 股。</li>
<li><b>資料來源</b>：使用 Yahoo Finance (yfinance)，部分 A 股的財務數據可能不完整。</li>
<li><b>時間點</b>：數據截止至 {datetime.now().strftime("%Y-%m-%d")}，股價隨時變動。</li>
<li><b>產業分類</b>：基於簡易名稱判斷，非正式產業分類標準。</li>
</ol>

<div class="disclaimer">
<b>免責聲明</b>：本報告僅供研究參考，不構成投資建議。投資有風險，入市需謹慎。
所有分析基於歷史數據和公開信息，不保證未來表現。請在做出任何投資決策前，進行自己的盡職調查。
</div>

<div class="footer">報告由 CCStockWorkEnv 自動產生 — {timestamp}</div>
</body></html>""")

    html = "\n".join(parts)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_cn_3yr_low_research.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML report saved: {filepath}")
    print(f"Sections: STRONG({len(strong)}), PASS({len(passed)}), WATCH({len(watch)}), EXCLUDE({len(excluded)})")
    return filepath


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate CN 3-year low research report")
    parser.add_argument("--format", choices=["md", "html", "both"], default="both",
                        help="Output format (default: both)")
    args = parser.parse_args()

    if args.format in ("md", "both"):
        generate_report()
    if args.format in ("html", "both"):
        generate_html_report()
