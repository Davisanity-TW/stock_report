#!/usr/bin/env python3
"""Render a markdown table for US tickers + key indicators from us_report_data.json."""

from __future__ import annotations

import argparse
import json


def fmt_num(x, nd=2):
    if x is None:
        return "NA"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "NA"


def fmt_int(x):
    if x is None:
        return "NA"
    try:
        return f"{int(x):,}"
    except Exception:
        return "NA"


def fmt_pct(x, nd=2):
    if x is None:
        return "NA"
    try:
        return f"{float(x):+.{nd}f}%"
    except Exception:
        return "NA"


def fmt_chg(x, nd=2):
    if x is None:
        return "NA"
    try:
        return f"{float(x):+.{nd}f}"
    except Exception:
        return "NA"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    args = ap.parse_args()

    data = json.load(open(args.json_path, "r", encoding="utf-8"))

    # Ticker table
    print("| Ticker | Close | Chg | Chg% | Volume | SourceDate |")
    print("|---|---:|---:|---:|---:|---|")

    for t, v in data.get("tickers", {}).items():
        if not v.get("ok"):
            print(f"| {t} | NA | NA | NA | NA | NA |")
            continue
        print("| {t} | {close} | {chg} | {pct} | {vol} | {d} |".format(
            t=t,
            close=fmt_num(v.get("close"), 2),
            chg=fmt_chg(v.get("chg"), 2),
            pct=fmt_pct(v.get("chg_pct"), 2),
            vol=fmt_int(v.get("volume")),
            d=v.get("date") or "NA",
        ))

    print("")
    print("| Indicator | Close | Chg | Chg% | SourceDate |")
    print("|---|---:|---:|---:|---|")
    for name in ["VIX", "XAUUSD", "XAGUSD", "BTCUSD"]:
        v = data.get("indicators", {}).get(name, {})
        if not v.get("ok"):
            print(f"| {name} | NA | NA | NA | NA |")
            continue
        print("| {name} | {close} | {chg} | {pct} | {d} |".format(
            name=name,
            close=fmt_num(v.get("close"), 2),
            chg=fmt_chg(v.get("chg"), 2),
            pct=fmt_pct(v.get("chg_pct"), 2),
            d=v.get("date") or "NA",
        ))


if __name__ == "__main__":
    main()
