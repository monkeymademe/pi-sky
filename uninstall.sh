#!/usr/bin/env bash
# Pi-Sky uninstaller — reset the system to retest install.sh
#
# Typical retest (remove Pi-Sky service + app, keep dump1090):
#   sudo ./uninstall.sh --yes
#
# Full clean slate for one-line installer retest (also removes dump1090-fa):
#   sudo ./uninstall.sh --yes --purge --with-dump1090
#
# Environment variables (same as install.sh):
#   PI_SKY_DIR=/home/pi/pi-sky
#   PI_SKY_USER=pi
#   PI_SKY_UNINSTALL_YES=1          Skip confirmation prompts

set -euo pipefail

PI_SKY_DIR="${PI_SKY_DIR:-/home/pi/pi-sky}"
PI_SKY_USER="${PI_SKY_USER:-pi}"
PI_SKY_UNINSTALL_YES="${PI_SKY_UNINSTALL_YES:-0}"

PURGE_DIR=0
REMOVE_DUMP1090=0
REMOVE_FLIGHTAWARE_REPO=0

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
Pi-Sky uninstaller

Usage:
  sudo ./uninstall.sh [options]

Options:
  --yes                 Do not ask for confirmation
  --purge               Remove the entire Pi-Sky directory (not just runtime files)
  --with-dump1090       Also remove dump1090-fa and disable skyaware lighttpd modules
  --with-fa-repo        Also remove flightaware-apt-repository (implies --with-dump1090)
  -h, --help            Show this help

Examples:
  # Retest installer but keep dump1090 decoder running
  sudo ./uninstall.sh --yes

  # Full reset before curl | bash one-line install test
  sudo ./uninstall.sh --yes --purge --with-dump1090

Environment:
  PI_SKY_DIR, PI_SKY_USER, PI_SKY_UNINSTALL_YES=1
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes) PI_SKY_UNINSTALL_YES=1 ;;
    --purge) PURGE_DIR=1 ;;
    --with-dump1090) REMOVE_DUMP1090=1 ;;
    --with-fa-repo) REMOVE_DUMP1090=1; REMOVE_FLIGHTAWARE_REPO=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

if [ "$EUID" -ne 0 ]; then
  exec sudo -E \
    PI_SKY_DIR="$PI_SKY_DIR" \
    PI_SKY_USER="$PI_SKY_USER" \
    PI_SKY_UNINSTALL_YES="$PI_SKY_UNINSTALL_YES" \
    bash "$0" "$@"
fi

if ! id "$PI_SKY_USER" &>/dev/null; then
  echo "ERROR: User '$PI_SKY_USER' does not exist" >&2
  exit 1
fi

PI_SKY_HOME="$(getent passwd "$PI_SKY_USER" | cut -d: -f6)"
if [ "$PI_SKY_DIR" = "/home/pi/pi-sky" ] && [ "$PI_SKY_USER" != "pi" ]; then
  PI_SKY_DIR="$PI_SKY_HOME/pi-sky"
fi

confirm() {
  local prompt="$1"
  if [ "$PI_SKY_UNINSTALL_YES" = "1" ]; then
    return 0
  fi
  printf '%s [y/N] ' "$prompt"
  local reply
  read -r reply
  case "$reply" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

show_plan() {
  cat <<EOF
This will:
  - Stop and disable flight-tracker.service
  - Remove /etc/systemd/system/flight-tracker.service
EOF
  if [ "$PURGE_DIR" = "1" ]; then
    printf '  - Delete entire directory: %s\n' "$PI_SKY_DIR"
  elif [ -d "$PI_SKY_DIR" ]; then
    printf '  - Remove runtime files under: %s\n' "$PI_SKY_DIR"
    printf '    (venv/, config.json, flights.db, inky_ready.png, *.db-shm, *.db-wal)\n'
    printf '  - Keep Pi-Sky source code in place\n'
  fi
  if [ "$REMOVE_DUMP1090" = "1" ]; then
    printf '  - apt remove dump1090-fa\n'
    printf '  - Disable skyaware / dump1090 lighttpd modules\n'
  fi
  if [ "$REMOVE_FLIGHTAWARE_REPO" = "1" ]; then
    printf '  - apt remove flightaware-apt-repository\n'
  fi
}

stop_pi_sky_service() {
  if systemctl list-unit-files flight-tracker.service &>/dev/null; then
    log "Stopping flight-tracker service"
    systemctl stop flight-tracker.service 2>/dev/null || true
    systemctl disable flight-tracker.service 2>/dev/null || true
  fi
  if [ -f /etc/systemd/system/flight-tracker.service ]; then
    rm -f /etc/systemd/system/flight-tracker.service
    systemctl daemon-reload
  fi
  if [ -f "$PI_SKY_HOME/.config/systemd/user/flight-tracker.service" ]; then
    log "Removing user systemd service"
    sudo -u "$PI_SKY_USER" systemctl --user stop flight-tracker.service 2>/dev/null || true
    sudo -u "$PI_SKY_USER" systemctl --user disable flight-tracker.service 2>/dev/null || true
    rm -f "$PI_SKY_HOME/.config/systemd/user/flight-tracker.service"
    sudo -u "$PI_SKY_USER" systemctl --user daemon-reload 2>/dev/null || true
  fi
}

remove_runtime_files() {
  [ -d "$PI_SKY_DIR" ] || return 0
  log "Removing Pi-Sky runtime files from $PI_SKY_DIR"
  rm -rf "$PI_SKY_DIR/venv"
  rm -f \
    "$PI_SKY_DIR/config.json" \
    "$PI_SKY_DIR/flights.db" \
    "$PI_SKY_DIR/flights.db-shm" \
    "$PI_SKY_DIR/flights.db-wal" \
    "$PI_SKY_DIR/inky_ready.png"
  rm -f "$PI_SKY_DIR"/config.json.backup.*
}

purge_pi_sky_dir() {
  if [ ! -d "$PI_SKY_DIR" ]; then
    return 0
  fi
  log "Removing Pi-Sky directory: $PI_SKY_DIR"
  rm -rf "$PI_SKY_DIR"
}

cleanup_lighttpd_installer_artifacts() {
  local dup changed=0
  for dup in 88-dump1090-fa-statcache.conf 89-skyaware.conf; do
    if [ -L "/etc/lighttpd/conf-enabled/$dup" ]; then
      rm -f "/etc/lighttpd/conf-enabled/$dup"
      changed=1
    fi
  done
  if [ "$changed" = "1" ]; then
    log "Removed duplicate lighttpd config links from a previous install"
  fi
}

remove_dump1090() {
  cleanup_lighttpd_installer_artifacts

  if command -v lighty-disable-mod &>/dev/null; then
    lighty-disable-mod skyaware 2>/dev/null || true
    lighty-disable-mod dump1090-fa-statcache 2>/dev/null || true
    lighty-disable-mod dump1090-fa 2>/dev/null || true
  fi

  if dpkg -s dump1090-fa &>/dev/null; then
    log "Removing dump1090-fa package"
    apt-get remove -y dump1090-fa
    apt-get autoremove -y
  fi

  systemctl stop dump1090-fa.service 2>/dev/null || true
  systemctl disable dump1090-fa.service 2>/dev/null || true

  if systemctl is-active lighttpd &>/dev/null; then
    systemctl try-restart lighttpd.service 2>/dev/null || true
  fi
}

remove_flightaware_repo() {
  if dpkg -s flightaware-apt-repository &>/dev/null; then
    log "Removing flightaware-apt-repository package"
    apt-get remove -y flightaware-apt-repository
  fi
}

main() {
  log "Pi-Sky uninstaller"
  show_plan
  confirm "Continue?" || { echo "Cancelled."; exit 0; }

  stop_pi_sky_service

  if [ "$PURGE_DIR" = "1" ]; then
    purge_pi_sky_dir
  else
    remove_runtime_files
    cleanup_lighttpd_installer_artifacts
  fi

  if [ "$REMOVE_DUMP1090" = "1" ]; then
    remove_dump1090
  fi

  if [ "$REMOVE_FLIGHTAWARE_REPO" = "1" ]; then
    remove_flightaware_repo
  fi

  cat <<EOF

============================================================
 Pi-Sky uninstall complete
============================================================

 Retest the one-line installer with:

   curl -fsSL https://raw.githubusercontent.com/monkeymademe/pi-sky/main/install.sh | sudo bash

 Or from a local clone:

   sudo ./install.sh

============================================================
EOF
}

main "$@"
