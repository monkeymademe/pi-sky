#!/bin/bash
# Install Pi-Sky as a user systemd service (no sudo for the unit file itself)

set -e

SERVICE_NAME="flight-tracker"
SERVICE_FILE="flight-tracker-user.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Installing Pi-Sky as a user service from $PROJECT_DIR..."

if [ ! -f "$PROJECT_DIR/$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $PROJECT_DIR/$SERVICE_FILE"
    exit 1
fi

mkdir -p "$USER_SYSTEMD_DIR"

echo "Copying service file to $USER_SYSTEMD_DIR..."
cp "$PROJECT_DIR/$SERVICE_FILE" "$USER_SYSTEMD_DIR/$SERVICE_NAME.service"
chmod 644 "$USER_SYSTEMD_DIR/$SERVICE_NAME.service"

echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Enabling service to start on boot (user session)..."
systemctl --user enable "$SERVICE_NAME.service"

echo "Enabling user service lingering (requires sudo once)..."
if command -v loginctl &> /dev/null; then
    sudo loginctl enable-linger "$USER" || true
fi

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
