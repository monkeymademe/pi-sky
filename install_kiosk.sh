#!/bin/bash
# Script to install flight-tracker-kiosk.service as a systemd service

set -e

SERVICE_NAME="flight-tracker-kiosk"
SERVICE_FILE="flight-tracker-kiosk.service"
PROJECT_DIR="/home/pi/berrybase_demos/flightaware_demo"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing Flight Tracker Kiosk service..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "This script needs to be run with sudo"
    echo "Usage: sudo ./install_kiosk.sh"
    exit 1
fi

# Check if service file exists
if [ ! -f "$PROJECT_DIR/$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $PROJECT_DIR/$SERVICE_FILE"
    exit 1
fi

# Check if kiosk script exists
if [ ! -f "$PROJECT_DIR/start_kiosk.sh" ]; then
    echo "Error: Kiosk script not found at $PROJECT_DIR/start_kiosk.sh"
    exit 1
fi

# Copy service file to systemd directory
echo "Copying service file to $SYSTEMD_DIR..."
cp "$PROJECT_DIR/$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_FILE"

# Set proper permissions
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service to start on boot
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


