#!/usr/bin/env bash
# CUPS smb-Backend mit Kerberos-Ticket des druckenden Users.
# Installation: Mode 0700, Owner root → cupsd startet uns als root.
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
  return 1
}

# CUPS übergibt: argv[1]=job-id argv[2]=user …
JOB_USER="${2:-}"
UID_NUM="${AUTH_UID:-}"

if [[ -z "${UID_NUM}" && -n "${JOB_USER}" ]]; then
  UID_NUM="$(id -u "${JOB_USER}" 2>/dev/null || true)"
fi

if [[ -n "${UID_NUM}" ]]; then
  if CC="$(pick_ccache "${UID_NUM}")"; then
    export KRB5CCNAME="${CC}"
  else
    echo "WARNING: kein Kerberos-ccache für uid=${UID_NUM} user=${JOB_USER}" >&2
  fi
fi

exec "$REAL_SMBSPOOL" "$@"
