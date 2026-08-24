#!/usr/bin/env bash
# Vor dem Display-Manager: alle NetworkManager-Systemverbindungen aktivieren.
set -euo pipefail

if ! command -v nmcli >/dev/null 2>&1; then
  exit 0
fi

# Warten bis NM antwortet
for _ in $(seq 1 30); do
  if nmcli -t general status >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Alle systemweiten Verbindungen (keine user-permissions) mit Autoconnect hochfahren
mapfile -t CONS < <(nmcli -t -f UUID,FILENAME connection show 2>/dev/null | while IFS=: read -r uuid file; do
  [[ -n "$uuid" ]] || continue
  # nur system-connections
  case "$file" in
    /etc/NetworkManager/system-connections/*) echo "$uuid" ;;
  esac
done)

for uuid in "${CONS[@]:-}"; do
  [[ -n "$uuid" ]] || continue
  # permissions leer = systemweit; Autoconnect egal — vor Login trotzdem versuchen
  perms="$(nmcli -g connection.permissions connection show uuid "$uuid" 2>/dev/null || true)"
  if [[ -n "$perms" ]]; then
    # User-gebundene Profile überspringen (Greeter hat keinen User)
    continue
  fi
  nmcli -w 25 connection up uuid "$uuid" >/dev/null 2>&1 || true
done

exit 0
