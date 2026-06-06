#!/bin/bash
# Install flight-tracker.service (Pi-Sky) as a systemd system service

set -e

SERVICE_NAME="flight-tracker"
SERVICE_FILE="flight-tracker.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing Pi-Sky service from $PROJECT_DIR..."

if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo"
    echo "Usage: sudo ./install_service.sh"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/$SERVICE_FILE" ]; then
    echo "Error: Service file not found at $PROJECT_DIR/$SERVICE_FILE"
    exit 1
fi

LEGACY_CONFIG="/home/pi/berrybase_demos/flightaware_demo/config.json"
if [ ! -f "$PROJECT_DIR/config.json" ] && [ -f "$LEGACY_CONFIG" ]; then
    echo "Copying config from legacy flight tracker install..."
    cp "$LEGACY_CONFIG" "$PROJECT_DIR/config.json"
    chown pi:pi "$PROJECT_DIR/config.json"
fi

if [ ! -f "$PROJECT_DIR/config.json" ]; then
    echo "Note: No config.json yet. Copy from template after install:"
    echo "  cp $PROJECT_DIR/config_template.json $PROJECT_DIR/config.json"
fi

chmod +x "$PROJECT_DIR/start_flight_tracker.sh"

PI_USER="${SUDO_USER:-$USER}"
PI_HOME="$(getent passwd "$PI_USER" | cut -d: -f6)"

echo "Writing service file to $SYSTEMD_DIR (user=$PI_USER, dir=$PROJECT_DIR)..."
cat >"$SYSTEMD_DIR/$SERVICE_FILE" <<EOF
[Unit]
Description=Pi-Sky server
After=network-online.target dump1090-fa.service lighttpd.service
Wants=network-online.target dump1090-fa.service

[Service]
Type=simple
User=${PI_USER}
Group=${PI_USER}
WorkingDirectory=${PROJECT_DIR}
Environment="HOME=${PI_HOME}"
Environment="USER=${PI_USER}"
Environment="PATH=${PROJECT_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/bin/bash ${PROJECT_DIR}/start_flight_tracker.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=false

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME.service"

echo ""
echo "✓ Service installed successfully!"
echo ""
echo "To start the service now, run:"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
echo "To check service status, run:"
echo "  sudo systemctl status $SERVICE_NAME"
echo ""
echo "To view service logs, run:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "To stop the service, run:"
echo "  sudo systemctl stop $SERVICE_NAME"
echo ""
echo "To disable auto-start on boot, run:"
echo "  sudo systemctl disable $SERVICE_NAME"
