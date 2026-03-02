#!/usr/bin/env python3
"""
Shared configuration loader for CCStockWorkEnv.

Reads the project-root config.json and provides typed access to credentials.

Usage:
    from config import load_config, get_telegram_config, get_email_config
"""

import json
import os
import sys

# Walk up from any tool_scripts subdirectory to find project root
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "config.json.template")


def load_config() -> dict:
    """Load the project-root config.json."""
    if not os.path.exists(CONFIG_PATH):
        print(f"ERROR: config.json not found at {CONFIG_PATH}")
        print(f"Copy config.json.template to config.json and fill in your credentials:")
        print(f"  cp {TEMPLATE_PATH} {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_telegram_config() -> dict:
    """Return telegram section: {bot_token, chat_ids}.

    Supports both legacy 'chat_id' (single string) and 'chat_ids' (list).
    Always returns 'chat_ids' as a list and 'chat_id' as the first entry.
    """
    tg = load_config()["telegram"]
    # Normalize: support both chat_id (legacy) and chat_ids (list)
    if "chat_ids" in tg:
        chat_ids = tg["chat_ids"]
    elif "chat_id" in tg:
        chat_ids = [tg["chat_id"]]
    else:
        chat_ids = []
    tg["chat_ids"] = chat_ids
    tg["chat_id"] = chat_ids[0] if chat_ids else None
    return tg


def get_email_config() -> dict:
    """Return email section: {mailgun_api_key, mailgun_domain, from_email, to_emails}."""
    return load_config()["email"]


def get_api_keys() -> dict:
    """Return api_keys section (may contain nulls for unused keys)."""
    return load_config().get("api_keys", {})
