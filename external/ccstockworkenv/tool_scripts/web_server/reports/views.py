"""
Views for reports app
"""
import json
import subprocess
import re
from datetime import datetime, timedelta
from pathlib import Path

from django.shortcuts import render
from django.conf import settings
from django.http import Http404, JsonResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .report_scanner import scan_reports
from .system_scanner import scan_commands, scan_skills, scan_schedules, get_system_status

MARKET_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "market_data"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.json"


def _build_absolute_origins():
    """Build list of absolute URL origins to strip from report HTML.

    Reads config.json for web server IP/ports. Any matching origin prefix
    in report HTML (e.g. http://localhost:8800/charts/...) gets stripped
    to a relative path (/charts/...), so iframes work on mobile.
    """
    origins = ['http://localhost:8800']
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            ws = config.get('web_server', {})
            ip = ws.get('fixed_ip')
            ext_port = ws.get('external_port')
            int_port = ws.get('internal_port', 8800)
            if ip and ext_port:
                origins.append(f'http://{ip}:{ext_port}')
            if ip and int_port:
                origins.append(f'http://{ip}:{int_port}')
            if int_port and int_port != 8800:
                origins.append(f'http://localhost:{int_port}')
        except (json.JSONDecodeError, OSError):
            pass
    # Sort longest first so more specific origins match before shorter ones
    origins.sort(key=len, reverse=True)
    return origins


_ABSOLUTE_ORIGINS = _build_absolute_origins()


def _normalize_report_urls(content: str) -> str:
    """Replace absolute localhost/external-IP URLs with relative paths."""
    for origin in _ABSOLUTE_ORIGINS:
        content = content.replace(origin, '')
    return content

PERIOD_DAYS = {
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "3y": 1095,
    "5y": 1825,
}


def dashboard(request):
    """System dashboard - homepage"""
    reports = scan_reports(settings.REPORTS_OUTPUT_DIR)
    commands = scan_commands()
    skills = scan_skills()
    schedules = scan_schedules()
    status = get_system_status()

    return render(request, 'reports/dashboard.html', {
        'reports': reports[:5],  # Latest 5 reports
        'total_reports': len(reports),
        'commands': commands,
        'skills': skills,
        'schedules': schedules,
        'status': status,
    })


def report_list(request):
    """Display list of all reports"""
    reports = scan_reports(settings.REPORTS_OUTPUT_DIR)

    return render(request, 'reports/list.html', {
        'reports': reports,
        'total_count': len(reports),
    })


def report_detail(request, slug):
    """Display detailed report content"""
    reports = scan_reports(settings.REPORTS_OUTPUT_DIR)
    report = next((r for r in reports if r['url_slug'] == slug), None)

    if not report:
        raise Http404("報告不存在")

    # Prefer HTML over MD
    file_path = report['html_path'] or report['md_path']

    if not file_path:
        raise Http404("報告檔案不存在")

    # Read file content
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_content = f.read()

    if file_path.suffix == '.html':
        # Extract <style> from <head> (original report CSS)
        style_blocks = re.findall(r'<style[^>]*>(.*?)</style>', raw_content, re.DOTALL)
        inline_css = '\n'.join(style_blocks) if style_blocks else ''

        # Extract content between <body> tags
        body_match = re.search(r'<body[^>]*>(.*)</body>', raw_content, re.DOTALL)
        content = body_match.group(1) if body_match else raw_content

        # Normalize absolute URLs to relative paths (fixes iframe on mobile)
        content = _normalize_report_urls(content)
    else:
        inline_css = ''
        content = f'<pre>{raw_content}</pre>'

    return render(request, 'reports/detail.html', {
        'report': report,
        'content': content,
        'inline_css': inline_css,
    })


def _fetch_price_history(ticker, market, days):
    """Call fetcher_factory.py via subprocess and return parsed JSON."""
    result = subprocess.run(
        ["uv", "run", "python", "fetcher_factory.py", "history", ticker,
         "--market", market, "--days", str(days)],
        cwd=str(MARKET_DATA_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    # stdout contains JSON array, stderr has record count — parse stdout only
    return json.loads(result.stdout)


def _fetch_company_info(ticker, market):
    """Call fetcher_factory.py info via subprocess."""
    result = subprocess.run(
        ["uv", "run", "python", "fetcher_factory.py", "info", ticker,
         "--market", market],
        cwd=str(MARKET_DATA_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def api_price_history(request):
    """API endpoint: returns OHLCV JSON for a ticker."""
    ticker = request.GET.get("ticker", "").strip()
    market = request.GET.get("market", "US").strip().upper()
    period = request.GET.get("period", "1y").strip().lower()

    if not ticker:
        return JsonResponse({"error": "Missing ticker parameter"}, status=400)

    if market not in ("US", "TW", "CN"):
        return JsonResponse({"error": f"Unsupported market: {market}"}, status=400)

    days = PERIOD_DAYS.get(period, 365)

    try:
        records = _fetch_price_history(ticker, market, days)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        return JsonResponse({"error": str(e)}, status=500)

    # Fetch company info for display name
    info = _fetch_company_info(ticker, market)
    company_name = info.get("name", ticker) if info else ticker

    return JsonResponse({
        "ticker": ticker,
        "market": market,
        "period": period,
        "company_name": company_name,
        "records": records,
    })


@xframe_options_sameorigin
def chart_page(request, ticker):
    """Render interactive chart page."""
    market = request.GET.get("market", "US").strip().upper()
    period = request.GET.get("period", "1y").strip().lower()
    embed = request.GET.get("embed", "0") == "1"

    if market not in ("US", "TW", "CN"):
        raise Http404("不支援的市場")

    if period not in PERIOD_DAYS:
        period = "1y"

    template = "reports/chart_embed.html" if embed else "reports/chart.html"

    return render(request, template, {
        "ticker": ticker,
        "market": market,
        "period": period,
    })
