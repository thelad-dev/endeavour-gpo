#!/usr/bin/env bash
# CUPS smb-Backend mit Kerberos-Ticket des druckenden Users.
# Läuft als root (Mode 0700), ruft danach /usr/bin/smbspool auf.
set -euo pipefail

REAL_SMBSPOOL=/usr/bin/smbspool
if [[ ! -x "$REAL_SMBSPOOL" ]]; then
  echo "ERROR: $REAL_SMBSPOOL fehlt" >&2
  exit 1
fi

pick_ccache() {
  local uid="$1" c
  for c in \
    "/tmp/krb5cc_${uid}" \
    "/run/user/${uid}/krb5cc" \
    "/run/user/${uid}/krb5ccache"
  do
    if [[ -e "$c" ]]; then
      if [[ -d "$c" ]]; then
        echo "DIR:${c}"
      else
        echo "FILE:${c}"
      fi
      return 0
    fi
  done
  # gssproxy / keyring variants
  if [[ -n "${uid}" ]]; then
    echo "KEYRING:persistent:${uid}"
    return 0
  fi
  return 1
}

UID_NUM="${AUTH_UID:-}"
if [[ -z "${UID_NUM}" && -n "${USER:-}" ]]; then
  UID_NUM="$(id -u "${USER}" 2>/dev/null || true)"
fi

if [[ -n "${UID_NUM}" ]]; then
  if CC="$(pick_ccache "${UID_NUM}")"; then
    export KRB5CCNAME="${CC}"
  fi
fi

exec "$REAL_SMBSPOOL" "$@"
