#!/bin/bash
# Create Python venv under Pi-Sky and install dependencies (run as user pi)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d venv ]; then
    echo "Creating virtualenv at $SCRIPT_DIR/venv ..."
    python3 -m venv venv
fi

echo "Installing Python dependencies..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "Done. The systemd units expect: $SCRIPT_DIR/venv/bin/python"
