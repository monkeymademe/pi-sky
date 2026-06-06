#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/venv/bin/activate"
fi
exec python3 flight_tracker_server.py
