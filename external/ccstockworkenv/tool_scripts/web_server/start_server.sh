#!/bin/bash
# CCStockWorkEnv Web Server Startup Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/data/webserver.log"
PID_FILE="$PROJECT_ROOT/data/webserver.pid"

# Check if server is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Web server already running (PID: $PID)"
        exit 0
    fi
fi

# Load config to get internal port (the port Django listens on)
PORT=$(python3 -c "
import json
with open('$PROJECT_ROOT/config.json') as f:
    ws = json.load(f).get('web_server', {})
    print(ws.get('internal_port', ws.get('port', 8800)))
" 2>/dev/null || echo 8800)

# Ensure Django DB exists (auto-create after fresh clone)
cd "$SCRIPT_DIR"
uv run python manage.py migrate --run-syncdb > /dev/null 2>&1

# Start server
nohup uv run python manage.py runserver 0.0.0.0:$PORT > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "✅ Web server started on port $PORT (PID: $!)"
echo "📋 View logs: tail -f $LOG_FILE"
echo "🌐 Access: http://localhost:$PORT"
