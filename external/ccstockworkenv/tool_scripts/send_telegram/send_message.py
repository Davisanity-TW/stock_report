#!/usr/bin/env python3
"""
Send messages to Telegram using the bot API.

Usage:
    python send_message.py --message "Your message here"
    python send_message.py --file /path/to/message.txt           # read file, send content as text
    python send_message.py --send-file /path/to/report.txt       # send file as document attachment
    python send_message.py --send-file /path/to/report.txt --caption "Daily report"
    python send_message.py --chat_id <CHAT_ID> --message "msg"   # override chat_id

To get your chat_id:
    1. Start a chat with your bot
    2. Send any message to the bot
    3. Run: python send_message.py --get_updates
"""

import argparse
import json
import os
import sys
import time
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "shared"))
from config import get_telegram_config


def load_config():
    """Load telegram config from shared project-root config.json."""
    tg = get_telegram_config()
    return {
        "TELEGRAM_BOT_TOKEN": tg["bot_token"],
        "TELEGRAM_CHAT_IDS": tg["chat_ids"],
    }


TELEGRAM_MAX_LENGTH = 4096


def split_message(message: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split a message into chunks that fit within Telegram's character limit.

    Tries to split at paragraph breaks first, then sentence breaks, then word breaks.
    """
    if len(message) <= max_length:
        return [message]

    chunks = []
    remaining = message

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Find a good split point within max_length
        chunk = remaining[:max_length]

        # Try to split at paragraph break (double newline)
        split_idx = chunk.rfind('\n\n')
        if split_idx > max_length // 2:
            chunks.append(remaining[:split_idx].rstrip())
            remaining = remaining[split_idx:].lstrip()
            continue

        # Try to split at single newline
        split_idx = chunk.rfind('\n')
        if split_idx > max_length // 2:
            chunks.append(remaining[:split_idx].rstrip())
            remaining = remaining[split_idx:].lstrip()
            continue

        # Try to split at sentence end
        for sep in ['。', '. ', '！', '？', '! ', '? ']:
            split_idx = chunk.rfind(sep)
            if split_idx > max_length // 2:
                split_idx += len(sep)
                chunks.append(remaining[:split_idx].rstrip())
                remaining = remaining[split_idx:].lstrip()
                break
        else:
            # Try to split at space (word boundary)
            split_idx = chunk.rfind(' ')
            if split_idx > max_length // 2:
                chunks.append(remaining[:split_idx].rstrip())
                remaining = remaining[split_idx:].lstrip()
                continue

            # Hard split at max_length as last resort
            chunks.append(remaining[:max_length])
            remaining = remaining[max_length:]

    return chunks


def _post_with_retry(url: str, payload: dict, max_attempts: int = 3) -> requests.Response:
    """POST with retry and escalating timeouts for unstable networks."""
    timeouts = [60, 90, 120]
    for attempt in range(max_attempts):
        timeout = timeouts[min(attempt, len(timeouts) - 1)]
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            return response
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            if attempt == max_attempts - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"Attempt {attempt + 1}/{max_attempts} failed ({e.__class__.__name__}), retrying in {wait}s...")
            time.sleep(wait)


def send_message(bot_token: str, chat_id: str, message: str) -> dict:
    """Send a message to a Telegram chat. Automatically splits long messages."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    chunks = split_message(message)
    results = []

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML"
        }
        response = _post_with_retry(url, payload)
        response.raise_for_status()
        results.append(response.json())

    # Return last result for compatibility, but include chunk count
    final_result = results[-1] if results else {}
    final_result["_chunks_sent"] = len(chunks)
    return final_result


def _post_multipart_with_retry(url: str, data: dict, files: dict, max_attempts: int = 3) -> requests.Response:
    """POST multipart/form-data with retry and escalating timeouts."""
    timeouts = [60, 90, 120]
    for attempt in range(max_attempts):
        timeout = timeouts[min(attempt, len(timeouts) - 1)]
        try:
            response = requests.post(url, data=data, files=files, timeout=timeout)
            return response
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            if attempt == max_attempts - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"Attempt {attempt + 1}/{max_attempts} failed ({e.__class__.__name__}), retrying in {wait}s...")
            time.sleep(wait)


def send_document(bot_token: str, chat_id: str, file_path: str, caption: str | None = None) -> dict:
    """Send a file as a document attachment to a Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        response = _post_multipart_with_retry(url, data=data, files=files)

    response.raise_for_status()
    return response.json()


def get_updates(bot_token: str) -> dict:
    """Get recent updates/messages sent to the bot (useful for finding chat_id)."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Send messages to Telegram")
    parser.add_argument("--chat_id", type=str, help="Telegram chat ID to send message to")
    parser.add_argument("--message", type=str, help="Message text to send")
    parser.add_argument("--file", type=str, help="Path to file; reads content and sends as text message")
    parser.add_argument("--send-file", type=str, dest="send_file",
                        help="Path to file; sends the file itself as a document attachment")
    parser.add_argument("--caption", type=str, help="Caption for document attachment (used with --send-file)")
    parser.add_argument("--get_updates", action="store_true",
                        help="Get recent updates to find chat_id")

    args = parser.parse_args()
    config = load_config()
    bot_token = config["TELEGRAM_BOT_TOKEN"]

    if args.get_updates:
        updates = get_updates(bot_token)
        print(json.dumps(updates, indent=2, ensure_ascii=False))

        # Extract chat IDs from updates
        if updates.get("result"):
            print("\n--- Chat IDs found ---")
            seen_chats = {}
            for update in updates["result"]:
                if "message" in update:
                    chat = update["message"]["chat"]
                    chat_id = chat["id"]
                    if chat_id not in seen_chats:
                        seen_chats[chat_id] = chat
                        chat_type = chat.get("type", "unknown")
                        if chat_type == "private":
                            name = f"{chat.get('first_name', '')} {chat.get('last_name', '')}".strip()
                        else:
                            name = chat.get("title", "Unknown")
                        print(f"  chat_id: {chat_id} | type: {chat_type} | name: {name}")
        return

    # Determine target chat_ids
    if args.chat_id:
        chat_ids = [args.chat_id]
    else:
        chat_ids = config.get("TELEGRAM_CHAT_IDS", [])
    if not chat_ids:
        print("Error: --chat_id is required (or set chat_ids in config.json)")
        sys.exit(1)

    # Send file as document attachment
    if args.send_file:
        for cid in chat_ids:
            result = send_document(bot_token, cid, args.send_file, caption=args.caption)
            if result.get("ok"):
                print(f"Document sent successfully to chat_id: {cid} ({os.path.basename(args.send_file)})")
            else:
                print(f"Failed to send document to {cid}: {result}")
                sys.exit(1)
        return

    # Get message from args or file (send as text)
    if args.file:
        with open(args.file, "r", encoding="utf8") as f:
            message = f.read()
    elif args.message:
        message = args.message
    else:
        print("Error: Either --message, --file, or --send-file is required")
        sys.exit(1)

    for cid in chat_ids:
        result = send_message(bot_token, cid, message)

        if result.get("ok"):
            chunks_sent = result.get("_chunks_sent", 1)
            if chunks_sent > 1:
                print(f"Message sent successfully to chat_id: {cid} ({chunks_sent} chunks)")
            else:
                print(f"Message sent successfully to chat_id: {cid}")
        else:
            print(f"Failed to send message to {cid}: {result}")
            sys.exit(1)


if __name__ == "__main__":
    main()
