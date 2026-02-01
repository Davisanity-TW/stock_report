#!/usr/bin/env python3
"""Fetch Moltbook posts and write a small curated digest for David.

- Uses Moltbook API: https://www.moltbook.com/api/v1
- Reads API key from /home/ubuntu/clawd/secrets/moltbook.json
- Writes to stock_report repo: reports/moltbook/YYYY-MM-DD.md
- Appends sections so later times go lower in the file.

Curation: simple keyword scoring (MinIO/K8s/storage/markets/AI infra).
"""

from __future__ import annotations

import json
import os
import re
import time
import datetime as dt
from pathlib import Path
import urllib.request

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

API_BASE = "https://www.moltbook.com/api/v1"
CREDS_PATH = Path("/home/ubuntu/clawd/secrets/moltbook.json")
STATE_PATH = Path("/home/ubuntu/clawd/memory/moltbook-digest-state.json")

KEYWORDS = {
    # infra/storage
    "minio": 5,
    "s3": 2,
    "erasure": 3,
    "healing": 3,
    "kubernetes": 4,
    "k8s": 4,
    "cni": 2,
    "etcd": 2,
    "storage": 3,
    "nvme": 2,
    "ceph": 3,
    "prometheus": 2,
    "grafana": 2,
    # markets
    "vix": 2,
    "nasdaq": 2,
    "sp500": 2,
    "s&p": 2,
    "gold": 2,
    "silver": 2,
    "bitcoin": 2,
    "btc": 2,
    # ai infra
    "inference": 2,
    "llm": 2,
    "gpu": 2,
}


def tz_now():
    if ZoneInfo is None:
        return dt.datetime.now()
    return dt.datetime.now(tz=ZoneInfo("Asia/Taipei"))


def http_json(url: str, api_key: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "molt/stock_report digest",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_state():
    if not STATE_PATH.exists():
        return {"seen_ids": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": []}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def score_post(p: dict) -> int:
    text = " ".join([
        str(p.get("title") or ""),
        str(p.get("content") or ""),
        str(p.get("url") or ""),
        str((p.get("submolt") or {}).get("name") or ""),
    ]).lower()
    s = 0
    for k, w in KEYWORDS.items():
        if k in text:
            s += w
    # small bonus for non-empty link posts
    if p.get("url"):
        s += 1
    return s


def render_entry(p: dict, score: int) -> str:
    title = (p.get("title") or "(no title)").strip()
    content = (p.get("content") or "").strip()
    url = p.get("url")
    sub = (p.get("submolt") or {}).get("name")
    pid = p.get("id")
    created = p.get("created_at")

    lines = []
    lines.append(f"- **{title}**")
    lines.append(f"  - submolt: `{sub}` | score: `{score}` | created: `{created}`")
    if pid:
        lines.append(f"  - post_id: `{pid}`")
    if url:
        lines.append(f"  - link: {url}")
    if content:
        # keep it short
        snippet = re.sub(r"\s+", " ", content)
        if len(snippet) > 240:
            snippet = snippet[:240] + "…"
        lines.append(f"  - snippet: {snippet}")
    return "\n".join(lines)


def main():
    creds = json.loads(CREDS_PATH.read_text(encoding="utf-8"))
    api_key = creds["api_key"]

    now = tz_now()
    day = now.date().isoformat()
    hhmm = now.strftime("%H:%M")

    # Fetch new posts globally (safe default)
    j = http_json(f"{API_BASE}/posts?sort=new&limit=25", api_key)
    posts = j.get("posts") or []

    state = load_state()
    seen = set(state.get("seen_ids") or [])

    scored = []
    for p in posts:
        pid = p.get("id")
        if pid and pid in seen:
            continue
        s = score_post(p)
        scored.append((s, p))

    scored.sort(key=lambda x: (x[0], x[1].get("created_at") or ""), reverse=True)
    top = [p for s, p in scored if s > 0][:8]

    out_dir = Path("reports/moltbook")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{day}.md"

    if not out_file.exists():
        out_file.write_text(f"# Moltbook ideas digest ({day})\n\n", encoding="utf-8")

    block_lines = []
    block_lines.append(f"## {day} {hhmm} (Asia/Taipei)\n")
    if not top:
        block_lines.append("- （本輪沒有找到明顯相關的貼文；可能只是今天內容偏雜談。）")
    else:
        block_lines.append("以下是我覺得你可能有興趣的貼文（依關聯分數排序）：")
        for p in top:
            block_lines.append(render_entry(p, score_post(p)))
    block_lines.append("")

    out_file.write_text(out_file.read_text(encoding="utf-8") + "\n" + "\n".join(block_lines), encoding="utf-8")

    # update seen ids
    for p in posts:
        pid = p.get("id")
        if pid:
            seen.add(pid)
    state["seen_ids"] = list(seen)[-500:]
    save_state(state)

    print(str(out_file))


if __name__ == "__main__":
    main()
