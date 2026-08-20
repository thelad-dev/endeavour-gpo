#!/usr/bin/env bash
# Blockiert System-Sleep solange Netzteil (AC) online ist.
# Aufruf: ac-sleep-guard.sh on|off|sync
set -euo pipefail

PIDFILE=/run/endeavour-gpo-ac-sleep-guard.pid
WHY="endeavour-gpo: kein Sleep am Netzteil"

is_ac_online() {
  local f online=0
  for f in /sys/class/power_supply/*/type; do
    [[ -f "$f" ]] || continue
    [[ "$(cat "$f")" == "Mains" ]] || continue
    local dir online_file
    dir="$(dirname "$f")"
    online_file="$dir/online"
    [[ -f "$online_file" ]] || continue
    if [[ "$(cat "$online_file")" == "1" ]]; then
      online=1
      break
    fi
  done
  [[ "$online" -eq 1 ]]
}

start_inhibit() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    return 0
  fi
  systemd-inhibit --what=sleep --who=endeavour-gpo --why="$WHY" --mode=block \
    /usr/bin/sleep infinity &
  echo $! >"$PIDFILE"
}

stop_inhibit() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  # leftover inhibitors from previous boots
  pkill -f "systemd-inhibit --what=sleep --who=endeavour-gpo" 2>/dev/null || true
}

case "${1:-}" in
  on) start_inhibit ;;
  off) stop_inhibit ;;
  sync)
    if is_ac_online; then start_inhibit; else stop_inhibit; fi
    ;;
  *)
    echo "Usage: $0 on|off|sync" >&2
    exit 2
    ;;
esac
