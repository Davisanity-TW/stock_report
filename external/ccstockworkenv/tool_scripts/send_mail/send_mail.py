#!/usr/bin/env python3
"""
Send emails via Mailgun API.

Usage:
    cd tool_scripts/send_mail
    uv run python send_mail.py --subject "Test" --body "Hello"
    uv run python send_mail.py --subject "Report" --html-file report.html --attachment chart1.png --attachment chart2.png
    uv run python send_mail.py --to override@example.com --subject "Test" --body "Hello"
"""

import argparse
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from config import get_email_config


def send_email(
    api_key: str,
    domain: str,
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
    html: str = None,
    attachments: list[str] = None,
) -> dict:
    """Send an email via Mailgun API.

    Args:
        attachments: List of file paths to attach.
    """
    url = f"https://api.mailgun.net/v3/{domain}/messages"

    data = {
        "from": from_email,
        "to": to_email,
        "subject": subject,
        "text": body,
    }

    if html:
        data["html"] = html

    files = []
    opened_files = []
    try:
        if attachments:
            for path in attachments:
                f = open(path, "rb")
                opened_files.append(f)
                files.append(("attachment", (os.path.basename(path), f)))

        response = requests.post(
            url,
            auth=("api", api_key),
            data=data,
            files=files if files else None,
            timeout=60,
        )
    finally:
        for f in opened_files:
            f.close()

    if response.status_code == 200:
        return {"success": True, "response": response.json()}
    else:
        return {
            "success": False,
            "status_code": response.status_code,
            "error": response.text,
        }


def main():
    parser = argparse.ArgumentParser(description="Send email via Mailgun API")
    parser.add_argument("--to", help="Recipient email address (overrides config)")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body", help="Email body text")
    parser.add_argument("--file", help="Read email body from file")
    parser.add_argument("--html", help="HTML body (optional)")
    parser.add_argument("--html-file", help="Read HTML body from file")
    parser.add_argument("--attachment", action="append", dest="attachments",
                        help="File to attach (repeatable)")
    parser.add_argument("--from", dest="from_email", help="Override sender email")

    args = parser.parse_args()

    config = get_email_config()

    # Determine recipients
    if args.to:
        to_emails = [args.to]
    else:
        to_emails = config.get("to_emails", [])
        if not to_emails:
            print("ERROR: No recipients specified. Use --to or set to_emails in config.json")
            sys.exit(1)

    # Determine email body
    body = ""
    if args.body:
        body = args.body
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"ERROR: File not found: {args.file}")
            sys.exit(1)
        with open(file_path, "r", encoding="utf-8") as f:
            body = f.read()
    elif args.html or args.html_file:
        body = "(see HTML version)"
    else:
        print("ERROR: Either --body, --file, --html, or --html-file must be provided")
        sys.exit(1)

    # Determine HTML body (optional)
    html = None
    if args.html:
        html = args.html
    elif args.html_file:
        html_path = Path(args.html_file)
        if not html_path.exists():
            print(f"ERROR: HTML file not found: {args.html_file}")
            sys.exit(1)
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

    # Validate attachments exist
    if args.attachments:
        for path in args.attachments:
            if not os.path.exists(path):
                print(f"ERROR: Attachment not found: {path}")
                sys.exit(1)

    from_email = args.from_email or config["from_email"]

    print(f"Subject: {args.subject}")
    print(f"From: {from_email}")
    print(f"Body length: {len(body)} chars")
    if html:
        print(f"HTML length: {len(html)} chars")
    if args.attachments:
        print(f"Attachments: {len(args.attachments)}")
        for p in args.attachments:
            print(f"  - {os.path.basename(p)}")
    print(f"Recipients: {len(to_emails)}")
    print()

    success_count = 0
    for to_email in to_emails:
        print(f"Sending to: {to_email}...")

        result = send_email(
            api_key=config["mailgun_api_key"],
            domain=config["mailgun_domain"],
            from_email=from_email,
            to_email=to_email,
            subject=args.subject,
            body=body,
            html=html,
            attachments=args.attachments,
        )

        if result["success"]:
            print(f"  Sent! Message ID: {result['response'].get('id', 'N/A')}")
            success_count += 1
        else:
            print(f"  ERROR: {result.get('status_code')} - {result.get('error')}")

    print()
    print(f"Done: {success_count}/{len(to_emails)} emails sent successfully")


if __name__ == "__main__":
    main()
