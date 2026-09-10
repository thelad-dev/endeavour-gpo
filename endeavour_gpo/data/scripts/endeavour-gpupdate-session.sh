#!/bin/bash
# Apply user GPOs (CIFS drive maps + AD-Home) after a graphical AD login.
# Invoked from systemd --user (graphical-session.target), then re-execs via sudo.
set -u

SCRIPT="$(readlink -f "$0")"
AD_UID_MIN="${ENDEAVOUR_GPO_AD_UID_MIN:-20000}"

log() {
  echo "$*"
  command -v logger >/dev/null 2>&1 && logger -t endeavour-gpupdate-session -- "$*" || true
}

is_local_account() {
  local name="$1"
  grep -q "^${name}:" /etc/passwd
}

if [[ "$(id -u)" -ne 0 ]]; then
  me="$(id -un)"
  if is_local_account "$me"; then
    log "skip local user ${me}"
    exit 0
  fi
  if [[ "$(id -u)" -lt "$AD_UID_MIN" ]]; then
    log "skip uid $(id -u) < ${AD_UID_MIN}"
    exit 0
  fi
  exec /usr/bin/sudo -n "$SCRIPT"
fi

USER_NAME="${SUDO_USER:-}"
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  log "no SUDO_USER; skip"
  exit 0
fi
if is_local_account "$USER_NAME"; then
  log "skip local user ${USER_NAME}"
  exit 0
fi

USER_UID="$(id -u "$USER_NAME")"
USER_GID="$(id -g "$USER_NAME")"
USER_HOME="$(getent passwd "$USER_NAME" | awk -F: '{print $6}')"

if [[ "$(id -u "$USER_NAME")" -lt "$AD_UID_MIN" ]]; then
  log "skip uid ${USER_UID} < ${AD_UID_MIN}"
  exit 0
fi

ccache="/tmp/krb5cc_${USER_UID}"
if [[ ! -e "$ccache" ]]; then
  for f in /tmp/krb5cc_${USER_UID}_*; do
    [[ -e "$f" ]] || continue
    ccache="$f"
    break
  done
fi
export KRB5CCNAME="FILE:${ccache}"

deadline=$((SECONDS + 45))
while (( SECONDS < deadline )); do
  if klist -s 2>/dev/null; then
    break
  fi
  sleep 1
done
if ! klist -s 2>/dev/null; then
  log "warn: no Kerberos ticket for ${USER_NAME} (${KRB5CCNAME}); trying anyway"
fi

rc=0
/usr/bin/endeavour-gpupdate --force --user -U "$USER_NAME" || rc=$?

EXTRA="/etc/endeavour-gpo/extra-drives.conf"
if [[ -f "$EXTRA" && -n "$USER_HOME" ]]; then
  mkdir -p "${USER_HOME}/netzlaufwerke"
  while read -r src name _rest || [[ -n "${src:-}" ]]; do
    [[ -z "${src:-}" || "$src" == \#* ]] && continue
    [[ -z "${name:-}" ]] && continue
    target="${USER_HOME}/netzlaufwerke/${name}"
    mkdir -p "$target"
    if mountpoint -q "$target"; then
      log "already mounted: $target"
      continue
    fi
    if mount -t cifs "$src" "$target" -o "uid=${USER_UID},gid=${USER_GID},file_mode=0644,dir_mode=0755,nosuid,nodev,sec=krb5,cruid=${USER_UID},_netdev"; then
      log "mounted extra ${src} -> ${target}"
    else
      log "warn: extra mount failed ${src} -> ${target}"
    fi
  done < "$EXTRA"
fi

exit "$rc"
