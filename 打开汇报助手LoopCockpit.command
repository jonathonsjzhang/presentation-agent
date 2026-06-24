#!/bin/zsh
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PYTHON="/Users/zhangsijing/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi

PORT="$("$PYTHON" - <<'PY'
import socket

for port in range(8765, 8786):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        if sock.connect_ex(("127.0.0.1", port)) != 0:
            print(port)
            break
else:
    raise SystemExit("No free port found between 8765 and 8785")
PY
)"

URL="http://127.0.0.1:${PORT}/"
echo "Starting 汇报助手 Loop Cockpit..."
echo "Project: $ROOT_DIR"
echo "URL: $URL"
echo ""
echo "Keep this window open while using the cockpit."
echo "Press Ctrl+C here to stop the local server."
echo ""

open "$URL"
"$PYTHON" -m presentation_agent.web --host 127.0.0.1 --port "$PORT"
