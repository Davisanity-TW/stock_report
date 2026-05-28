#!/usr/bin/env python3
"""Fetch TAIFEX after-hours TX futures quote and print a Telegram-ready summary."""

from __future__ import annotations

import datetime as dt
import re
import sys
from zoneinfo import ZoneInfo

import requests


def clean_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^<]+?>", " ", text)).strip()


def main() -> int:
    day = dt.datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d")
    url = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
    form = {"queryDate": day, "commodity_id": "TX", "MarketCode": "1"}

    try:
        html = requests.post(url, data=form, timeout=30).text
        table = re.search(r'<table[^>]*class="table_f[\s\S]*?</table>', html)
        if not table:
            raise RuntimeError("parse_error: table_f not found")

        row = None
        for tr in re.findall(r"<tr[^>]*>[\s\S]*?</tr>", table.group(0)):
            txt = clean_html(tr)
            if txt.startswith("TX "):
                row = txt
                break
        if not row:
            raise RuntimeError("parse_error: TX row not found")

        parts = row.split()
        contract = parts[1]
        last = parts[5]
        change = parts[6].replace("▼", "-").replace("▲", "+")
        pct = parts[7].replace("▼", "-").replace("▲", "+")
        volume = parts[8]
        print(
            f"台指期盤後（TAIFEX TX，{contract}） {day.replace('/', '-')}\n"
            f"行情：{last}\n"
            f"漲跌：{change}（{pct}）\n"
            f"成交量：{volume}\n"
            "連結：https://www.wantgoo.com/futures/wtxp&"
        )
        return 0
    except Exception as exc:
        print(
            "目前無法自動擷取台指期盤後數字。\n"
            f"原因：{exc}\n"
            "連結：https://www.wantgoo.com/futures/wtxp&",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
