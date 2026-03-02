"""
System scanner - scans project structure for commands, skills, schedulers, and status
"""
from pathlib import Path
import subprocess
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def scan_commands() -> list[dict]:
    """Scan .claude/commands/ for available commands"""
    commands_dir = PROJECT_ROOT / '.claude' / 'commands'
    if not commands_dir.exists():
        return []

    commands = []
    for f in sorted(commands_dir.glob('*.md')):
        name = f.stem
        # Read first line for title
        with open(f, 'r', encoding='utf-8') as fh:
            first_line = fh.readline().strip()

        title = first_line.lstrip('# ').strip()

        # Read second paragraph for description
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()

        # Extract description (first non-empty line after title)
        lines = content.split('\n')
        description = ''
        for line in lines[1:]:
            line = line.strip()
            if line and not line.startswith('#'):
                description = line
                break

        commands.append({
            'name': name,
            'slash': f'/{name}',
            'title': title,
            'description': description,
        })

    return commands


def scan_skills() -> list[dict]:
    """Scan .claude/skills/ for domain knowledge"""
    skills_dir = PROJECT_ROOT / '.claude' / 'skills'
    if not skills_dir.exists():
        return []

    skills = []
    for f in sorted(skills_dir.glob('*.md')):
        name = f.stem
        with open(f, 'r', encoding='utf-8') as fh:
            first_line = fh.readline().strip()

        title = first_line.lstrip('# ').strip()

        skills.append({
            'name': name,
            'title': title,
        })

    return skills


def scan_schedules() -> list[dict]:
    """Scan schedules/ directory and launchd for scheduled tasks"""
    schedules_dir = PROJECT_ROOT / 'schedules'
    launch_agents_dir = Path.home() / 'Library' / 'LaunchAgents'

    schedules = []

    # Scan plist files
    if launch_agents_dir.exists():
        for f in sorted(launch_agents_dir.glob('com.ccstockworkenv.*.plist')):
            name = f.stem.replace('com.ccstockworkenv.', '')

            # Parse plist for schedule info
            schedule_info = _parse_plist_schedule(f)

            # Check if running
            status = _check_launchd_status(f.stem)

            schedules.append({
                'name': name,
                'plist': f.name,
                'schedule': schedule_info,
                'status': status,
                'has_script': (schedules_dir / f'{name}.sh').exists() if schedules_dir.exists() else False,
            })

    return schedules


def _parse_plist_schedule(plist_path: Path) -> str:
    """Extract schedule description from plist"""
    try:
        content = plist_path.read_text()

        if 'StartCalendarInterval' in content:
            # Extract hour and minute
            hour_match = re.search(r'<key>Hour</key>\s*<integer>(\d+)</integer>', content)
            minute_match = re.search(r'<key>Minute</key>\s*<integer>(\d+)</integer>', content)
            weekday_match = re.search(r'<key>Weekday</key>\s*<integer>(\d+)</integer>', content)

            hour = int(hour_match.group(1)) if hour_match else 0
            minute = int(minute_match.group(1)) if minute_match else 0

            if weekday_match:
                days = ['日', '一', '二', '三', '四', '五', '六']
                day = days[int(weekday_match.group(1))]
                return f'每週{day} {hour:02d}:{minute:02d}'
            else:
                return f'每日 {hour:02d}:{minute:02d}'

        elif 'StartInterval' in content:
            interval_match = re.search(r'<key>StartInterval</key>\s*<integer>(\d+)</integer>', content)
            if interval_match:
                seconds = int(interval_match.group(1))
                if seconds >= 3600:
                    return f'每 {seconds // 3600} 小時'
                else:
                    return f'每 {seconds // 60} 分鐘'

        elif 'KeepAlive' in content and 'RunAtLoad' in content:
            return '持續運行 (服務)'

        return '未知'
    except Exception:
        return '讀取失敗'


def _check_launchd_status(label: str) -> str:
    """Check if a launchd job is loaded and running"""
    try:
        result = subprocess.run(
            ['launchctl', 'list'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if label in line:
                parts = line.split('\t')
                pid = parts[0].strip() if len(parts) > 0 else '-'
                if pid != '-' and pid.isdigit():
                    return 'running'
                return 'loaded'
        return 'not loaded'
    except Exception:
        return 'unknown'


def get_system_status() -> dict:
    """Get overall system status"""
    import json

    # Database
    db_path = PROJECT_ROOT / 'data' / 'ccstockworkenv.db'
    db_status = 'ok' if db_path.exists() else 'missing'
    db_size = f'{db_path.stat().st_size / 1024 / 1024:.1f} MB' if db_path.exists() else '-'

    # Config
    config_path = PROJECT_ROOT / 'config.json'
    config_status = 'ok' if config_path.exists() else 'missing'

    # Web server URL
    web_url = 'http://localhost:8800'
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
            ws = config.get('web_server', {})
            ip = ws.get('fixed_ip', 'localhost')
            port = ws.get('external_port', ws.get('port', 8800))
            web_url = f'http://{ip}:{port}'
        except Exception:
            pass

    # Reports count
    output_dir = PROJECT_ROOT / 'output'
    report_count = len(list(output_dir.glob('*.html'))) if output_dir.exists() else 0
    md_count = len(list(output_dir.glob('*.md'))) if output_dir.exists() else 0

    # Charts count
    charts_dir = PROJECT_ROOT / 'data' / 'charts'
    chart_count = len(list(charts_dir.glob('*.png'))) if charts_dir.exists() else 0

    return {
        'db_status': db_status,
        'db_size': db_size,
        'config_status': config_status,
        'web_url': web_url,
        'report_count': report_count,
        'md_count': md_count,
        'chart_count': chart_count,
    }
