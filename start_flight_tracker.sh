#!/bin/bash
set -e
cd /home/pi/pi-sky
if [ -f /home/pi/pi-sky/venv/bin/activate ]; then
  # shellcheck source=/dev/null
  source /home/pi/pi-sky/venv/bin/activate
fi
exec python3 flight_tracker_server.py
