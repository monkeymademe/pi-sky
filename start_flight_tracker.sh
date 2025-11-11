#!/bin/bash
source /home/pi/flightaware-venv/bin/activate
cd /home/pi/berrybase_demos/flightaware_demo
exec python flight_tracker_server.py
