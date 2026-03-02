"""
Report scanner - scans output/ directory for generated reports
"""
from pathlib import Path
from datetime import datetime
import json
import re


# Type display name mapping (known report types → Chinese names)
TYPE_DISPLAY_NAMES = {
    'cn_3yr_low_research': '中國A股三年低點研究',
    'screening': '篩選結果報告',
    'comparison': '股票對比分析',
    'sector': '產業概覽報告',
}

# Prefix-based display names
TYPE_PREFIX_NAMES = {
    'single_': '個股深度分析',
    'comparison_': '股票對比分析',
    'sector_': '產業概覽報告',
    'screening_': '篩選結果報告',
}


def _extract_html_title(html_path: Path) -> str | None:
    """Extract <title> content from an HTML file's first 2KB."""
    try:
        html_head = html_path.read_text(encoding='utf-8')[:2000]
        match = re.search(r'<title>(.+?)</title>', html_head)
        if match:
            title = match.group(1).strip()
            # Strip common suffixes like " — CCStockWorkEnv"
            title = re.sub(r'\s*[—–-]\s*CCStockWorkEnv$', '', title)
            return title if title else None
    except OSError:
        pass
    return None


def _resolve_display_name(type_str: str, html_path: Path | None = None,
                          metadata_path: Path | None = None) -> str:
    """Resolve display name with priority: metadata.json > HTML <title> > known types > slug.

    This ensures Chinese titles appear on the homepage. The .title() English
    fallback is only used as an absolute last resort.
    """
    # Priority 1: metadata.json title
    if metadata_path and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            if metadata.get('title'):
                return metadata['title']
        except (json.JSONDecodeError, OSError):
            pass

    # Priority 2: HTML <title> tag
    if html_path and html_path.exists():
        title = _extract_html_title(html_path)
        if title:
            return title

    # Priority 3: Known type mappings
    name = TYPE_DISPLAY_NAMES.get(type_str)
    if name:
        return name

    # Priority 4: Prefix-based mappings
    for prefix, display in TYPE_PREFIX_NAMES.items():
        if type_str.startswith(prefix):
            if prefix == 'single_':
                ticker = type_str.replace('single_', '').split('_')[0].upper()
                return f'{display} ({ticker})'
            return display

    # Priority 5 (last resort): slug as-is (no .title() to avoid English-style names)
    return type_str.replace('_', ' ')


def parse_report_name(name: str) -> dict | None:
    """
    Parse report filename or directory name to extract metadata.

    Supported formats (canonical — timestamp first):
        YYYYMMDD_HHMM_<type>.{html|md}       (file)
        YYYYMMDD_HHMMSS_<type>.{html|md}     (file, 6-digit time)
        YYYYMMDD_HHMM_<type>                 (directory)
        YYYYMMDD_HHMMSS_<type>               (directory)

    Also handles reversed format (legacy — type first):
        <type>_YYYYMMDD_HHMMSS               (directory)
        <type>_YYYYMMDD_HHMMSS.{html|md}     (file)

    Args:
        name: Filename or directory name

    Returns:
        dict with parsed data or None if invalid format
    """
    # Try canonical patterns first (timestamp at start)
    pattern_file = r'^(\d{8})_(\d{4,6})_(.+)\.(html|md)$'
    pattern_dir = r'^(\d{8})_(\d{4,6})_(.+)$'

    # Reversed patterns (type at start, timestamp at end)
    pattern_reversed_file = r'^(.+)_(\d{8})_(\d{4,6})\.(html|md)$'
    pattern_reversed_dir = r'^(.+)_(\d{8})_(\d{4,6})$'

    match = re.match(pattern_file, name)
    ext = None
    if match:
        date_str, time_str, type_str, ext = match.groups()
    else:
        match = re.match(pattern_dir, name)
        if match:
            date_str, time_str, type_str = match.groups()
        else:
            # Try reversed patterns as fallback
            match = re.match(pattern_reversed_file, name)
            if match:
                type_str, date_str, time_str, ext = match.groups()
            else:
                match = re.match(pattern_reversed_dir, name)
                if match:
                    type_str, date_str, time_str = match.groups()
                else:
                    return None

    # Parse datetime (support both HHMM and HHMMSS)
    try:
        if len(time_str) == 6:
            date = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
        else:
            date = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M")
    except ValueError:
        return None

    return {
        'timestamp': f"{date_str}_{time_str}",
        'type': type_str,
        'date': date,
        'extension': ext,  # None for directories
    }


def scan_reports(output_dir: Path) -> list[dict]:
    """
    Scan output directory for reports

    Args:
        output_dir: Path to output/ directory

    Returns:
        List of report dicts, sorted by date descending (newest first)
        Each dict contains:
        - timestamp: str (e.g., "20260228_2349")
        - type: str (e.g., "cn_3yr_low_research")
        - date: datetime
        - html_path: Path to HTML file (or None)
        - md_path: Path to MD file (or None)
        - display_name: str (e.g., "中國A股三年低點研究")
        - url_slug: str (for URL, e.g., "20260228_2349_cn_3yr_low_research")
    """
    if not output_dir.exists():
        return []

    # Collect all report files
    reports_by_slug = {}

    for entry in output_dir.iterdir():
        if entry.is_file():
            # Flat file report: YYYYMMDD_HHMM_type.html
            parsed = parse_report_name(entry.name)
            if not parsed or not parsed['extension']:
                continue

            slug = f"{parsed['timestamp']}_{parsed['type']}"

            if slug not in reports_by_slug:
                html_path = entry if parsed['extension'] == 'html' else None
                display_name = _resolve_display_name(
                    parsed['type'], html_path=html_path)

                reports_by_slug[slug] = {
                    'timestamp': parsed['timestamp'],
                    'type': parsed['type'],
                    'date': parsed['date'],
                    'html_path': None,
                    'md_path': None,
                    'display_name': display_name,
                    'url_slug': slug,
                }

            if parsed['extension'] == 'html':
                reports_by_slug[slug]['html_path'] = entry
            elif parsed['extension'] == 'md':
                reports_by_slug[slug]['md_path'] = entry

        elif entry.is_dir():
            # Directory-based report: YYYYMMDD_HHMMSS_type/index.html
            parsed = parse_report_name(entry.name)
            if not parsed:
                continue

            index_html = entry / 'index.html'
            index_md = entry / 'index.md'
            if not index_html.exists() and not index_md.exists():
                continue

            metadata_path = entry / 'metadata.json'
            html_path = index_html if index_html.exists() else None
            display_name = _resolve_display_name(
                parsed['type'], html_path=html_path, metadata_path=metadata_path)

            slug = f"{parsed['timestamp']}_{parsed['type']}"

            if slug not in reports_by_slug:
                reports_by_slug[slug] = {
                    'timestamp': parsed['timestamp'],
                    'type': parsed['type'],
                    'date': parsed['date'],
                    'html_path': html_path,
                    'md_path': index_md if index_md.exists() else None,
                    'display_name': display_name,
                    'url_slug': slug,
                }

    # Convert to list and sort by date descending
    reports = list(reports_by_slug.values())
    reports.sort(key=lambda r: r['date'], reverse=True)

    return reports
