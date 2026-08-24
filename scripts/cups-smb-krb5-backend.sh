#!/usr/bin/env bash
# CUPS smb-Backend mit Kerberos des Job-Users.
#
# Ablauf:
# 1) AUTH_UID aus Job-User (argv[2]), falls cupsd ihn nicht setzt
# 2) Spool-Datei nach /tmp kopieren und dem Job-User geben
#    (offizieller Wrapper macht setuid → /var/spool/cups/d… ist sonst unlesbar)
# 3) smbspool_krb5_wrapper ausführen
#
# Niemals /usr/bin/smbspool überschreiben.
set -euo pipefail

OFFICIAL=/usr/lib/samba/samba/smbspool_krb5_wrapper
REAL_SMBSPOOL=/usr/bin/smbspool

JOB_ID="${1:-}"
JOB_USER="${2:-}"
TITLE="${3:-}"
COPIES="${4:-}"
OPTIONS="${5:-}"
INFILE="${6:-}"

if [[ -z "${AUTH_UID:-}" && -n "${JOB_USER}" ]]; then
  AUTH_UID="$(id -u "${JOB_USER}" 2>/dev/null || true)"
fi
if [[ -n "${AUTH_UID:-}" ]]; then
  export AUTH_UID
fi
export AUTH_INFO_REQUIRED="${AUTH_INFO_REQUIRED:-negotiate}"

TMPJOB=""
cleanup() {
  [[ -n "${TMPJOB}" && -f "${TMPJOB}" ]] && rm -f "${TMPJOB}" || true
}
trap cleanup EXIT

ARGS=("${JOB_ID}" "${JOB_USER}" "${TITLE}" "${COPIES}" "${OPTIONS}")
if [[ -n "${INFILE}" ]]; then
  if [[ ! -f "${INFILE}" ]]; then
    echo "ERROR: Spool-Datei fehlt: ${INFILE}" >&2
    exit 1
  fi
  TMPJOB="$(mktemp /tmp/endeavour-gpo-print.XXXXXX)"
  cp -f "${INFILE}" "${TMPJOB}"
  if [[ -n "${AUTH_UID:-}" ]]; then
    chown "${AUTH_UID}:${AUTH_UID}" "${TMPJOB}"
  elif [[ -n "${JOB_USER}" ]]; then
    chown "${JOB_USER}:${JOB_USER}" "${TMPJOB}"
  fi
  chmod 600 "${TMPJOB}"
  ARGS+=("${TMPJOB}")
fi

if [[ -x "${OFFICIAL}" ]]; then
  "${OFFICIAL}" "${ARGS[@]}"
  exit $?
fi

if [[ ! -x "${REAL_SMBSPOOL}" ]]; then
  echo "ERROR: weder ${OFFICIAL} noch ${REAL_SMBSPOOL} gefunden" >&2
  exit 1
fi
echo "WARNING: offizieller smbspool_krb5_wrapper fehlt — Fallback smbspool" >&2
"${REAL_SMBSPOOL}" "${ARGS[@]}"
exit $?
