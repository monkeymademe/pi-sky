#!/bin/bash
# Install flight-tracker-kiosk.service (Pi-Sky fullscreen browser) as systemd

set -e

SERVICE_NAME="flight-tracker-kiosk"
SERVICE_FILE="flight-tracker-kiosk.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing Pi-Sky kiosk service from $PROJECT_DIR..."

if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo"
    echo "Usage: sudo ./install_kiosk.sh"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $PROJECT_DIR/$SERVICE_FILE"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/start_kiosk.sh" ]; then
    echo "Error: Kiosk script not found at $PROJECT_DIR/start_kiosk.sh"
    exit 1
fi

chmod +x "$PROJECT_DIR/start_kiosk.sh"

echo "Copying service file to $SYSTEMD_DIR..."
cp "$PROJECT_DIR/$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_FILE"
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME.service"

echo ""
echo "✓ Kiosk service installed successfully!"
echo ""
echo "Note: This service requires a graphical desktop environment."
echo "Make sure you're booting to desktop (not console) mode."
echo ""
echo "To start the kiosk mode now, run:"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
echo "To check service status, run:"
echo "  sudo systemctl status $SERVICE_NAME"
echo ""
echo "To view service logs, run:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "To stop the kiosk mode, run:"
echo "  sudo systemctl stop $SERVICE_NAME"
echo ""
echo "To disable auto-start on boot, run:"
echo "  sudo systemctl disable $SERVICE_NAME"
