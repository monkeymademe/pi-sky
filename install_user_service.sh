#!/bin/bash
# Script to install flight-tracker as a user systemd service
# This version doesn't require sudo - it installs as a user service

set -e

SERVICE_NAME="flight-tracker"
SERVICE_FILE="flight-tracker-user.service"
PROJECT_DIR="/home/pi/berrybase_demos/flightaware_demo"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Installing Flight Tracker as a user service..."

# Check if service file exists
if [ ! -f "$PROJECT_DIR/$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $PROJECT_DIR/$SERVICE_FILE"
    exit 1
fi

# Create user systemd directory if it doesn't exist
mkdir -p "$USER_SYSTEMD_DIR"

# Copy service file to user systemd directory
echo "Copying service file to $USER_SYSTEMD_DIR..."
cp "$PROJECT_DIR/$SERVICE_FILE" "$USER_SYSTEMD_DIR/$SERVICE_NAME.service"

# Set proper permissions
chmod 644 "$USER_SYSTEMD_DIR/$SERVICE_NAME.service"

# Reload systemd user daemon
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

# Enable service to start on boot (for user session)
echo "Enabling service to start on boot..."
systemctl --user enable "$SERVICE_NAME.service"

# Enable lingering so the service can start even when user is not logged in
echo "Enabling user service lingering..."
sudo loginctl enable-linger pi

echo ""
echo "✓ User service installed successfully!"
echo ""
echo "To start the service now, run:"
echo "  systemctl --user start $SERVICE_NAME"
echo ""
echo "To check service status, run:"
echo "  systemctl --user status $SERVICE_NAME"
echo ""
echo "To view service logs, run:"
echo "  journalctl --user -u $SERVICE_NAME -f"
echo ""
echo "To stop the service, run:"
echo "  systemctl --user stop $SERVICE_NAME"
echo ""
echo "To disable auto-start on boot, run:"
echo "  systemctl --user disable $SERVICE_NAME"

