#!/usr/bin/env bash
#
# Show dump1090 aircraft.json in the terminal; press a key to reload (q to quit).
#
# Uses dump1090_url from config.json in the repo root by default, or:
#   DUMP1090_URL=http://host/data/aircraft.json ./scripts/dump1090_aircraft_view.sh
#   ./scripts/dump1090_aircraft_view.sh 'http://localhost:8080/data/aircraft.json'
#
# Requires: curl, python3 (for pretty-printing JSON)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${DUMP1090_INSPECT_CONFIG:-$REPO_ROOT/config.json}"

resolve_url() {
  if [[ -n "${DUMP1090_URL:-}" ]]; then
    printf '%s' "$DUMP1090_URL"
    return
  fi
  if [[ -n "${1:-}" ]]; then
    printf '%s' "$1"
    return
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "No URL given and config not found: $CONFIG" >&2
    echo "Set DUMP1090_URL or pass the aircraft.json URL as the first argument." >&2
    exit 1
  fi
  python3 -c "
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    cfg = json.load(f)
u = cfg.get('dump1090_url', '').strip()
if not u:
    sys.exit('config.json has no dump1090_url')
print(u)
" "$CONFIG"
}

show_payload() {
  local body err
  err="$(mktemp)"
  if ! body="$(curl -sS --connect-timeout 3 --max-time 10 "$URL" 2>"$err")"; then
    echo "curl failed for: $URL" >&2
    cat "$err" >&2
    rm -f "$err"
    return 1
  fi
  rm -f "$err"
  if [[ -z "$body" ]]; then
    echo "(empty response)"
    return 0
  fi
  echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
}

URL="$(resolve_url "${1:-}")"

while true; do
  clear 2>/dev/null || printf '\n%.0s' {1..40}
  echo "dump1090 aircraft.json"
  echo "URL: $URL"
  echo "────────────────────────────────────────────────────────────"
  show_payload || true
  echo "────────────────────────────────────────────────────────────"
  echo "Any key = refresh again · q = quit"
  # -n 1: one keypress (no Enter needed); -s: do not echo the key
  IFS= read -r -n 1 -s key || true
  echo
  case "$key" in
    q|Q) exit 0 ;;
  esac
done
