#!/usr/bin/env bash
# endeavour-gpo — Installation auf einem domain-joined EndeavourOS/Arch-Client
# Aufruf: sudo ./scripts/install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte als root ausführen: sudo $0" >&2
  exit 1
fi

echo "==> 1/5 Paketabhängigkeiten (pacman)"
pacman -S --needed --noconfirm \
  samba \
  cifs-utils \
  cups \
  cups-filters \
  python-pip \
  python-cryptography \
  python-pycryptodome \
  libnotify \
  >/dev/null

systemctl enable --now cups.service winbind.service 2>/dev/null || true

echo "==> 2/5 Python-Paket installieren"
python3 -m pip install --upgrade --break-system-packages -e "$ROOT"

echo "==> 3/5 CSE registrieren + systemd/Timer/Socket/Session-Hook"
endeavour-gpo-register

echo "==> 4/5 Kurzprüfung"
command -v endeavour-gpupdate >/dev/null
command -v endeavour-gpo-register >/dev/null
testparm -s --parameter-name="apply group policies" 2>/dev/null || true
systemctl is-enabled endeavour-gpupdate.timer >/dev/null
systemctl is-enabled endeavour-gpupdate-remote.socket >/dev/null
systemctl --global is-enabled endeavour-gpupdate-session.service >/dev/null

echo "==> 5/5 Erste Richtlinienanwendung (aktueller sudo-User)"
if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != root ]]; then
  UID_NUM="$(id -u "$SUDO_USER")"
  export KRB5CCNAME="${KRB5CCNAME:-/tmp/krb5cc_${UID_NUM}}"
  if [[ -e "${KRB5CCNAME#FILE:}" || "${KRB5CCNAME}" == FILE:* || -e "/tmp/krb5cc_${UID_NUM}" ]]; then
    endeavour-gpupdate --force -U "$SUDO_USER" || {
      echo "Warnung: gpupdate fehlgeschlagen — später: sudo endeavour-gpupdate --force" >&2
    }
  else
    echo "Hinweis: kein Kerberos-Ticket für ${SUDO_USER} — bitte anmelden, dann:"
    echo "  sudo endeavour-gpupdate --force"
  fi
else
  echo "Hinweis: ohne SUDO_USER bitte nach Login:"
  echo "  sudo endeavour-gpupdate --force"
fi

cat <<'EOF'

Installation fertig.

Nächste Schritte:
  sudo endeavour-gpupdate --force          # wie Windows gpupdate /force
  ls ~/netzlaufwerke                      # Laufwerke
  lpstat -a                               # Drucker
  systemctl status endeavour-gpupdate.timer

Remote von einem Admin-PC:
  endeavour-gpupdate-remote nb64

EOF
