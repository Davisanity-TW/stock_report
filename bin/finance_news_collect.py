#!/usr/bin/env python3
"""Collect recent financial news from RSS sources defined in config/finance_sources.yaml.

Outputs JSON to stdout.

- Filters to items within the last N hours (default: 2)
- Dedup rules:
  - exact URL
  - title similarity > threshold (default from yaml: 0.9)

This script only collects + dedups; summarization is done by the calling agent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# YAML parser: use PyYAML if available; fallback to a minimal built-in loader for our config.
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

# No external RSS parser dependency; parse RSS/Atom via stdlib XML.

try:
    import requests  # type: ignore
except Exception:
    print("Missing dependency: requests. Install with: pip install requests", file=sys.stderr)
    raise

from difflib import SequenceMatcher
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def parse_dt_str(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    # RSS pubDate / Atom updated usually parseable here
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # ISO-ish fallback
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def canonical_url(u: str) -> str:
    u = (u or "").strip()
    # Google News RSS often uses long redirect links; keep as-is for exact-url dedup.
    return u


def title_norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def title_sim(a: str, b: str) -> float:
    a2, b2 = title_norm(a), title_norm(b)
    if not a2 or not b2:
        return 0.0
    return SequenceMatcher(None, a2, b2).ratio()


@dataclass
class Source:
    id: str
    name: str
    type: str
    url: Optional[str] = None
    url_template: Optional[str] = None
    query: Optional[str] = None
    language: Optional[str] = None
    weight: float = 1.0
    tags: List[str] = None


def load_sources(cfg: Dict[str, Any]) -> Dict[str, List[Source]]:
    def _read_block(block: Dict[str, Any]) -> List[Source]:
        out: List[Source] = []
        for tier in block.values():
            if not isinstance(tier, dict):
                continue
            for s in tier.get("sources", []) or []:
                out.append(
                    Source(
                        id=s.get("id"),
                        name=s.get("name"),
                        type=s.get("type"),
                        url=s.get("url"),
                        url_template=s.get("url_template"),
                        query=s.get("query"),
                        language=s.get("language"),
                        weight=float(s.get("weight", 1.0)),
                        tags=list(s.get("tags", []) or []),
                    )
                )
        return out

    return {
        "taiwan": _read_block(cfg.get("taiwan", {})),
        "global": _read_block(cfg.get("global_markets", {})),
    }


def build_url(src: Source) -> str:
    if src.type != "rss":
        raise ValueError(f"Unsupported source type: {src.type}")
    if src.url:
        return src.url
    if src.url_template and src.query is not None:
        from urllib.parse import quote

        return src.url_template.format(query=quote(src.query, safe=""))
    raise ValueError(f"Source {src.id} missing url or url_template")


def fetch_xml(url: str) -> ET.Element:
    headers = {
        "User-Agent": "clawdbot/stock_report (+https://github.com/Davisanity-TW/stock_report)",
        "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    }
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    # Some feeds may include invalid chars; be forgiving.
    content = r.content
    return ET.fromstring(content)


def parse_items(root: ET.Element) -> List[Dict[str, Any]]:
    # RSS 2.0: <rss><channel><item>...
    items: List[Dict[str, Any]] = []

    # Atom: <feed><entry>
    def strip_ns(tag: str) -> str:
        return tag.split('}', 1)[-1] if '}' in tag else tag

    # Build a simple iterator of item-like nodes
    candidates: List[ET.Element] = []
    if strip_ns(root.tag) == "rss":
        channel = next((c for c in root if strip_ns(c.tag) == "channel"), None)
        if channel is not None:
            candidates = [c for c in channel if strip_ns(c.tag) == "item"]
    elif strip_ns(root.tag) == "feed":
        candidates = [c for c in root if strip_ns(c.tag) == "entry"]

    for it in candidates:
        # title
        title = _text(next((c for c in it if strip_ns(c.tag) == "title"), None))

        # link
        link = ""
        if strip_ns(root.tag) == "feed":
            # Atom: <link href="..."/>
            for l in it.findall('./{*}link'):
                href = l.attrib.get('href')
                rel = l.attrib.get('rel', 'alternate')
                if href and rel == 'alternate':
                    link = href
                    break
            if not link:
                l = it.find('./{*}link')
                if l is not None and l.attrib.get('href'):
                    link = l.attrib['href']
        else:
            link = _text(next((c for c in it if strip_ns(c.tag) == "link"), None))

        # date
        dt = None
        for key in ("pubDate", "published", "updated"):
            dt = parse_dt_str(_text(next((c for c in it if strip_ns(c.tag) == key), None)))
            if dt:
                break

        # summary/description
        summary = _text(next((c for c in it if strip_ns(c.tag) in ("description", "summary", "content")), None))

        if not title and not link:
            continue

        items.append({"title": title, "link": link, "published_at": dt.isoformat() if dt else None, "raw_summary": summary})

    return items


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal YAML subset parser for this repo's config (handles dict/list/scalars).
    # If you hit parsing issues, install PyYAML in a venv.
    import json as _json
    try:
        # allow JSON as a fallback format
        return _json.loads(text)
    except Exception:
        raise RuntimeError("PyYAML not available and config is not valid JSON. Please install PyYAML in a venv.")


def collect(cfg_path: str, window_hours: float) -> Dict[str, Any]:
    cfg = _load_yaml(cfg_path)

    threshold = float(
        (cfg.get("global", {})
            .get("deduplication", {})
            .get("rules", [{} , {}])[1]
            .get("threshold", 0.9))
    )

    sources = load_sources(cfg)
    cutoff = now_utc() - timedelta(hours=window_hours)

    def _collect_one(src: Source) -> List[Dict[str, Any]]:
        url = build_url(src)
        root = fetch_xml(url)
        parsed = parse_items(root)
        items: List[Dict[str, Any]] = []
        for e in parsed:
            dt = None
            if e.get("published_at"):
                try:
                    dt = datetime.fromisoformat(str(e["published_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
                except Exception:
                    dt = None
            if not dt:
                continue
            if dt < cutoff:
                continue
            link = e.get("link") or ""
            title = (e.get("title") or "").strip()
            summary = (e.get("raw_summary") or "").strip()
            items.append(
                {
                    "title": title,
                    "link": canonical_url(link),
                    "published_at": dt.isoformat(),
                    "source": src.name,
                    "source_id": src.id,
                    "language": src.language,
                    "weight": src.weight,
                    "tags": src.tags or [],
                    "raw_summary": summary,
                    "feed_url": url,
                }
            )
        return items

    def _dedup(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_url = set()
        kept: List[Dict[str, Any]] = []
        for it in sorted(items, key=lambda x: (x.get("published_at", ""), x.get("weight", 0.0)), reverse=True):
            u = it.get("link") or ""
            if u and u in seen_url:
                continue

            is_dup = False
            for k in kept:
                if title_sim(it.get("title", ""), k.get("title", "")) >= threshold:
                    # merge: keep higher weight/newer as primary, append sources
                    k.setdefault("alt_links", [])
                    if u and u not in k["alt_links"] and u != k.get("link"):
                        k["alt_links"].append(u)
                    k.setdefault("alt_sources", [])
                    if it.get("source") and it.get("source") not in k["alt_sources"] and it.get("source") != k.get("source"):
                        k["alt_sources"].append(it.get("source"))
                    is_dup = True
                    break

            if is_dup:
                continue

            kept.append(it)
            if u:
                seen_url.add(u)

        return kept

    out: Dict[str, Any] = {
        "generated_at": now_utc().isoformat(),
        "window_hours": window_hours,
        "cutoff_utc": cutoff.isoformat(),
        "regions": {},
    }

    for region, srcs in sources.items():
        all_items: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for src in srcs:
            try:
                all_items.extend(_collect_one(src))
            except Exception as e:
                errors.append({"source": src.id, "error": str(e)})

        out["regions"][region] = {
            "items": _dedup(all_items),
            "errors": errors,
            "sources": [s.id for s in srcs],
        }

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/finance_sources.yaml")
    ap.add_argument("--window-hours", type=float, default=2.0)
    args = ap.parse_args()

    data = collect(args.config, args.window_hours)
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
