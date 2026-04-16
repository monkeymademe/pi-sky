#!/bin/bash
# Script to start Pi-Sky in kiosk mode
# This opens Chromium in fullscreen kiosk mode

CONFIG_FILE="/home/pi/pi-sky/config.json"
if [ -f "$CONFIG_FILE" ]; then
    HTTP_HOST=$(grep -o '"http_host": "[^"]*"' "$CONFIG_FILE" | cut -d'"' -f4)
    HTTP_PORT=$(grep -o '"http_port": [0-9]*' "$CONFIG_FILE" | grep -o '[0-9]*')

    if [ -z "$HTTP_HOST" ]; then
        HTTP_HOST="localhost"
    fi
    if [ -z "$HTTP_PORT" ]; then
        HTTP_PORT="5050"
    fi

    # 0.0.0.0 is a bind-all address, not a good browser target.
    if [ "$HTTP_HOST" = "0.0.0.0" ] || [ "$HTTP_HOST" = "::" ]; then
        HTTP_HOST="localhost"
    fi
else
    HTTP_HOST="localhost"
    HTTP_PORT="5050"
fi

# Construct the URL
URL="http://${HTTP_HOST}:${HTTP_PORT}/index-maps.html"

echo "Starting Pi-Sky in kiosk mode..."
echo "URL: $URL"

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide cursor after 3 seconds of inactivity (if unclutter is installed)
if command -v unclutter &> /dev/null; then
    unclutter -idle 3 &
else
    echo "Note: unclutter not installed. Cursor will remain visible."
    echo "Install with: sudo apt-get install unclutter"
fi

# Prefer chromium-browser (legacy) or chromium (current Raspberry Pi OS)
CHROME=""
if command -v chromium-browser &> /dev/null; then
    CHROME="chromium-browser"
elif command -v chromium &> /dev/null; then
    CHROME="chromium"
else
    echo "Error: Neither chromium-browser nor chromium found in PATH."
    exit 1
fi

# Start Chromium in kiosk mode
# --kiosk: Fullscreen mode
# --noerrdialogs: Suppress error dialogs
# --disable-infobars: Hide info bars
# --disable-session-crashed-bubble: Don't show crash recovery
# --disable-restore-session-state: Don't restore previous session
# --autoplay-policy=no-user-gesture-required: Allow autoplay
# --check-for-update-interval=31536000: Don't check for updates
# --disable-features=TranslateUI: Disable translation UI
# --disable-ipc-flooding-protection: Allow rapid IPC
"$CHROME" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    --disable-features=TranslateUI \
    --disable-ipc-flooding-protection \
    --disable-background-networking \
    --disable-background-timer-throttling \
    --disable-renderer-backgrounding \
    --disable-backgrounding-occluded-windows \
    --disable-breakpad \
    --disable-component-update \
    --disable-domain-reliability \
    --disable-features=AudioServiceOutOfProcess \
    --disable-hang-monitor \
    --disable-prompt-on-repost \
    --disable-sync \
    --disable-translate \
    --metrics-recording-only \
    --mute-audio \
    --no-default-browser-check \
    --no-first-run \
    --no-pings \
    --password-store=basic \
    --use-mock-keychain \
    --disable-web-security \
    --disable-features=VizDisplayCompositor \
    "$URL" &

# Wait for Chromium to start
sleep 2

# Keep script running
wait
