#!/usr/bin/env bash
# Pi-Sky one-line installer: dump1090-fa + Python venv + config + systemd services
#
# One-line install (from GitHub):
#   curl -fsSL https://raw.githubusercontent.com/monkeymademe/pi-sky/main/install.sh | sudo bash
#
# Local install (from a cloned repo):
#   sudo ./install.sh
#
# Options (environment variables):
#   PI_SKY_DIR=/home/pi/pi-sky     Install directory
#   PI_SKY_USER=pi                 Unix user to run Pi-Sky
#   PI_SKY_REPO=<git url>          Git clone URL (default: GitHub main)
#   PI_SKY_BRANCH=main             Git branch to install
#   PI_SKY_SKIP_DUMP1090=1         Skip dump1090-fa / FlightAware apt setup
#   PI_SKY_SKIP_SERVICE=1          Skip Pi-Sky systemd service install
#   PI_SKY_LAT=52.40               Receiver latitude (optional)
#   PI_SKY_LON=13.55               Receiver longitude (optional)

set -euo pipefail

PI_SKY_REPO="${PI_SKY_REPO:-https://github.com/monkeymademe/pi-sky.git}"
PI_SKY_BRANCH="${PI_SKY_BRANCH:-main}"
PI_SKY_DIR="${PI_SKY_DIR:-/home/pi/pi-sky}"
PI_SKY_USER="${PI_SKY_USER:-pi}"
PI_SKY_SKIP_DUMP1090="${PI_SKY_SKIP_DUMP1090:-0}"
PI_SKY_SKIP_SERVICE="${PI_SKY_SKIP_SERVICE:-0}"

FA_REPO_DEB_URLS=(
  "https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/flightaware-apt-repository/flightaware-apt-repository_1.3_all.deb"
  "https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/flightaware-apt-repository/flightaware-apt-repository_1.2_all.deb"
)

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if [ "$EUID" -ne 0 ]; then
  exec sudo -E \
    PI_SKY_DIR="$PI_SKY_DIR" \
    PI_SKY_USER="$PI_SKY_USER" \
    PI_SKY_REPO="$PI_SKY_REPO" \
    PI_SKY_BRANCH="$PI_SKY_BRANCH" \
    PI_SKY_SKIP_DUMP1090="$PI_SKY_SKIP_DUMP1090" \
    PI_SKY_SKIP_SERVICE="$PI_SKY_SKIP_SERVICE" \
    PI_SKY_LAT="${PI_SKY_LAT:-}" \
    PI_SKY_LON="${PI_SKY_LON:-}" \
    bash -s "$@"
fi

if ! id "$PI_SKY_USER" &>/dev/null; then
  die "User '$PI_SKY_USER' does not exist. Set PI_SKY_USER or create the account first."
fi

PI_SKY_HOME="$(getent passwd "$PI_SKY_USER" | cut -d: -f6)"
if [ -z "$PI_SKY_HOME" ]; then
  die "Could not resolve home directory for user '$PI_SKY_USER'"
fi

if [ "$PI_SKY_DIR" = "/home/pi/pi-sky" ] && [ "$PI_SKY_USER" != "pi" ]; then
  PI_SKY_DIR="$PI_SKY_HOME/pi-sky"
fi

install_apt_packages() {
  log "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    libcairo2-dev \
    pkg-config \
    wget
}

install_flightaware_repo() {
  if dpkg -s flightaware-apt-repository &>/dev/null; then
    log "FlightAware apt repository already installed"
    return 0
  fi

  log "Installing FlightAware apt repository"
  local tmp deb url
  tmp="$(mktemp -d)"
  for url in "${FA_REPO_DEB_URLS[@]}"; do
    if wget -q -O "$tmp/flightaware-apt-repository.deb" "$url"; then
      deb="$tmp/flightaware-apt-repository.deb"
      break
    fi
  done
  [ -n "${deb:-}" ] || die "Could not download flightaware-apt-repository package"
  dpkg -i "$deb"
  rm -rf "$tmp"
}

ensure_https_flightaware_apt() {
  local list="/etc/apt/sources.list.d/flightaware-apt-repository.list"
  [ -f "$list" ] || return 0
  if grep -q 'http://flightaware.com' "$list" 2>/dev/null; then
    log "Switching FlightAware apt source to HTTPS"
    sed -i 's|http://flightaware.com|https://flightaware.com|g' "$list"
  fi
}

install_dump1090_fa() {
  install_flightaware_repo
  ensure_https_flightaware_apt
  apt-get update -qq
  log "Installing dump1090-fa (includes lighttpd for aircraft.json on port 8080)"
  apt-get install -y dump1090-fa
}

cleanup_duplicate_lighttpd_links() {
  # Older installer versions created numeric-prefixed symlinks alongside
  # lighty-enable-mod links, which duplicates config and breaks lighttpd.
  local dup
  for dup in 88-dump1090-fa-statcache.conf 89-skyaware.conf; do
    if [ -L "/etc/lighttpd/conf-enabled/$dup" ]; then
      log "Removing duplicate lighttpd config link: $dup"
      rm -f "/etc/lighttpd/conf-enabled/$dup"
    fi
  done
}

setup_lighttpd_for_dump1090() {
  cleanup_duplicate_lighttpd_links

  mkdir -p /var/cache/lighttpd/uploads
  chown www-data:www-data /var/cache/lighttpd/uploads 2>/dev/null || true

  if command -v lighty-enable-mod &>/dev/null; then
    if ! grep -q -E '^\S*server\.stat-cache-engine' /etc/lighttpd/conf-enabled/*.conf 2>/dev/null; then
      lighty-enable-mod dump1090-fa-statcache 2>/dev/null || true
    fi
    lighty-enable-mod skyaware 2>/dev/null || true
  fi

  if lighttpd -tt -f /etc/lighttpd/lighttpd.conf >/tmp/pi-sky-lighttpd-test.log 2>&1; then
    systemctl enable lighttpd.service 2>/dev/null || true
    if systemctl restart lighttpd.service; then
      PI_SKY_DUMP1090_URL="${PI_SKY_DUMP1090_URL:-http://127.0.0.1:8080/data/aircraft.json}"
      return 0
    fi
  fi

  warn "lighttpd failed to start — Pi-Sky will read dump1090 JSON directly from disk"
  if [ -f /tmp/pi-sky-lighttpd-test.log ]; then
    tail -20 /tmp/pi-sky-lighttpd-test.log >&2 || true
  fi
  journalctl -u lighttpd -n 20 --no-pager >&2 2>/dev/null || true
  warn "Common causes: Pi-hole on port 80, duplicate lighttpd modules, or port conflicts"
  warn "Skyaware map on :8080 will be unavailable, but Pi-Sky will still work"
  PI_SKY_DUMP1090_URL="/run/dump1090-fa/aircraft.json"
  return 1
}

configure_dump1090_fa() {
  local conf="/etc/default/dump1090-fa"
  [ -f "$conf" ] || die "Missing $conf after dump1090-fa install"

  log "Configuring dump1090-fa"
  sed -i 's/^ENABLED=.*/ENABLED=yes/' "$conf"
  if ! grep -q '^RECEIVER=' "$conf"; then
    echo 'RECEIVER=rtlsdr' >>"$conf"
  else
    sed -i 's/^RECEIVER=.*/RECEIVER=rtlsdr/' "$conf"
  fi

  if [ -n "${PI_SKY_LAT:-}" ] && [ -n "${PI_SKY_LON:-}" ]; then
    if grep -q '^RECEIVER_LAT=' "$conf"; then
      sed -i "s/^RECEIVER_LAT=.*/RECEIVER_LAT=${PI_SKY_LAT}/" "$conf"
    else
      echo "RECEIVER_LAT=${PI_SKY_LAT}" >>"$conf"
    fi
    if grep -q '^RECEIVER_LON=' "$conf"; then
      sed -i "s/^RECEIVER_LON=.*/RECEIVER_LON=${PI_SKY_LON}/" "$conf"
    else
      echo "RECEIVER_LON=${PI_SKY_LON}" >>"$conf"
    fi
  fi

  systemctl daemon-reload
  systemctl enable dump1090-fa.service
  systemctl restart dump1090-fa.service
  setup_lighttpd_for_dump1090 || true
  export PI_SKY_DUMP1090_URL
}

resolve_receiver_coords() {
  python3 - <<'PY'
import json, os, re, urllib.request

lat = os.environ.get("PI_SKY_LAT", "").strip()
lon = os.environ.get("PI_SKY_LON", "").strip()
if lat and lon:
    print(json.dumps({"lat": float(lat), "lon": float(lon), "source": "env"}))
    raise SystemExit(0)

def from_piaware():
    path = "/var/cache/piaware/location.env"
    if not os.path.exists(path):
        return None
    vals = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^PIAWARE_(LAT|LON)="([^"]+)"', line.strip())
            if m:
                vals[m.group(1).lower()] = float(m.group(2))
    if "lat" in vals and "lon" in vals:
        return {"lat": vals["lat"], "lon": vals["lon"], "source": "piaware"}
    return None

def from_dump1090_defaults():
    path = "/etc/default/dump1090-fa"
    if not os.path.exists(path):
        return None
    vals = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^RECEIVER_(LAT|LON)=(.*)$", line.strip())
            if not m:
                continue
            raw = m.group(2).strip().strip('"').strip("'")
            if not raw:
                continue
            vals[m.group(1).lower()] = float(raw)
    if "lat" in vals and "lon" in vals:
        return {"lat": vals["lat"], "lon": vals["lon"], "source": "dump1090-fa"}
    return None

def from_ip():
    try:
        with urllib.request.urlopen("http://ip-api.com/json/?fields=status,lat,lon", timeout=8) as r:
            data = json.load(r)
        if data.get("status") == "success":
            return {"lat": float(data["lat"]), "lon": float(data["lon"]), "source": "ip-geolocation"}
    except Exception:
        pass
    return None

for fn in (from_piaware, from_dump1090_defaults, from_ip):
    hit = fn()
    if hit:
        print(json.dumps(hit))
        raise SystemExit(0)

print(json.dumps({"lat": 51.5074, "lon": -0.1278, "source": "default-london"}))
PY
}

ensure_pi_sky_source() {
  log "Installing Pi-Sky into $PI_SKY_DIR"
  if [ -d "$PI_SKY_DIR/.git" ]; then
    log "Updating existing git checkout"
    sudo -u "$PI_SKY_USER" git -C "$PI_SKY_DIR" fetch origin "$PI_SKY_BRANCH"
    sudo -u "$PI_SKY_USER" git -C "$PI_SKY_DIR" checkout "$PI_SKY_BRANCH"
    sudo -u "$PI_SKY_USER" git -C "$PI_SKY_DIR" pull --ff-only origin "$PI_SKY_BRANCH" || true
  elif [ -f "$PI_SKY_DIR/flight_tracker_server.py" ]; then
    log "Using existing Pi-Sky directory (not a git repo)"
  else
    sudo -u "$PI_SKY_USER" git clone --branch "$PI_SKY_BRANCH" --depth 1 "$PI_SKY_REPO" "$PI_SKY_DIR"
  fi
  chown -R "$PI_SKY_USER:$PI_SKY_USER" "$PI_SKY_DIR"
}

setup_python_venv() {
  log "Creating Python virtual environment and installing requirements"
  sudo -u "$PI_SKY_USER" bash -lc "cd '$PI_SKY_DIR' && ./setup_venv.sh"
}

write_config_json() {
  local coords_json lat lon source
  coords_json="$(resolve_receiver_coords)"
  lat="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d['lat'])" <<<"$coords_json")"
  lon="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d['lon'])" <<<"$coords_json")"
  source="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d['source'])" <<<"$coords_json")"

  if [ -f "$PI_SKY_DIR/config.json" ]; then
    log "Keeping existing config.json (not overwriting)"
    return 0
  fi

  log "Creating config.json (coordinates from $source)"
  python3 - <<PY
import json
import os
from pathlib import Path

template = json.loads(Path("$PI_SKY_DIR/config_template.json").read_text(encoding="utf-8"))
template["dump1090_url"] = os.environ.get(
    "PI_SKY_DUMP1090_URL",
    "http://127.0.0.1:8080/data/aircraft.json",
)
template["receiver_lat"] = float("$lat")
template["receiver_lon"] = float("$lon")
Path("$PI_SKY_DIR/config.json").write_text(
    json.dumps(template, indent=4) + "\n",
    encoding="utf-8",
)
PY
  chown "$PI_SKY_USER:$PI_SKY_USER" "$PI_SKY_DIR/config.json"
}

install_pi_sky_service() {
  log "Installing Pi-Sky systemd service"
  chmod +x "$PI_SKY_DIR/start_flight_tracker.sh"

  cat >/etc/systemd/system/flight-tracker.service <<EOF
[Unit]
Description=Pi-Sky server
After=network-online.target dump1090-fa.service lighttpd.service
Wants=network-online.target dump1090-fa.service

[Service]
Type=simple
User=${PI_SKY_USER}
Group=${PI_SKY_USER}
WorkingDirectory=${PI_SKY_DIR}
Environment="HOME=${PI_SKY_HOME}"
Environment="USER=${PI_SKY_USER}"
Environment="PATH=${PI_SKY_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/bin/bash ${PI_SKY_DIR}/start_flight_tracker.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=false

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable flight-tracker.service
  systemctl restart flight-tracker.service
}

wait_for_dump1090() {
  log "Waiting for dump1090 aircraft.json"
  local i url="${PI_SKY_DUMP1090_URL:-http://127.0.0.1:8080/data/aircraft.json}"
  for i in $(seq 1 30); do
    if [[ "$url" == /* ]] && [ -f "$url" ]; then
      return 0
    fi
    if curl -fsS --connect-timeout 2 --max-time 4 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  warn "dump1090 JSON not reachable yet at $url (Pi-Sky will retry when aircraft appear)"
}

wait_for_pi_sky() {
  local port
  port="$(python3 -c "import json; print(json.load(open('$PI_SKY_DIR/config.json'))['http_port'])" 2>/dev/null || echo 5050)"
  log "Waiting for Pi-Sky on port $port"
  local i
  for i in $(seq 1 30); do
    if curl -fsS --connect-timeout 2 --max-time 4 "http://127.0.0.1:${port}/events" -m 2 -o /dev/null 2>/dev/null; then
      return 0
    fi
    # Server may return non-200 on /events during SSE; try index page instead
    if curl -fsS --connect-timeout 2 --max-time 4 "http://127.0.0.1:${port}/index-maps.html" -o /dev/null 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  warn "Pi-Sky did not respond on port $port yet — check: sudo journalctl -u flight-tracker -n 50"
}

print_summary() {
  local port ip
  port="$(python3 -c "import json; print(json.load(open('$PI_SKY_DIR/config.json'))['http_port'])" 2>/dev/null || echo 5050)"
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$ip" ] || ip="127.0.0.1"

  cat <<EOF

============================================================
 Pi-Sky installation complete
============================================================

 Pi-Sky directory : $PI_SKY_DIR
 dump1090 source  : ${PI_SKY_DUMP1090_URL:-http://127.0.0.1:8080/data/aircraft.json}
 Pi-Sky map UI    : http://${ip}:${port}/index-maps.html
 Config page      : http://${ip}:${port}/config.html

 Services:
   sudo systemctl status dump1090-fa
   sudo systemctl status flight-tracker

 Logs:
   sudo journalctl -u dump1090-fa -f
   sudo journalctl -u flight-tracker -f

 Manual start (without systemd):
   cd $PI_SKY_DIR && ./venv/bin/python3 flight_tracker_server.py

 Plug in your ADS-B USB receiver if you have not already.
 Adjust receiver position in config.json or the config page if needed.
============================================================
EOF
}

main() {
  log "Pi-Sky installer"
  install_apt_packages

  if [ "$PI_SKY_SKIP_DUMP1090" != "1" ]; then
    install_dump1090_fa
    configure_dump1090_fa
    wait_for_dump1090
  else
    log "Skipping dump1090-fa install (PI_SKY_SKIP_DUMP1090=1)"
  fi

  ensure_pi_sky_source
  setup_python_venv
  write_config_json

  if [ "$PI_SKY_SKIP_SERVICE" != "1" ]; then
    install_pi_sky_service
    wait_for_pi_sky
  else
    log "Skipping Pi-Sky systemd service (PI_SKY_SKIP_SERVICE=1)"
  fi

  print_summary
}

main "$@"
