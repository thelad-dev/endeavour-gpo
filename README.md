# endeavour-gpo

Active-Directory-**Gruppenrichtlinien** auf **EndeavourOS** (und ähnliche Linux-Domänenclients):

| Was | Wie |
|-----|-----|
| Netzlaufwerke (GPP Drives + AD-Home) | `mount.cifs` unter `~/netzlaufwerke/<Buchstabe>_<Titel>/` |
| Netzwerkdrucker (GPP SharedPrinter) | CUPS-Queues `endeavour-<server>-<share>` mit Kerberos |
| Richtlinien aktualisieren | `endeavour-gpupdate` (wie Windows `gpupdate /force`) |
| Automatik | systemd-Timer (~90+0–30 min), Login-Hook, winbind `apply group policies` |
| Remote | SSH-Skript oder localhost-Socket `:46327` |

---

## Voraussetzungen

- Domain-joined Client (Samba/`winbind`, Realm `…`)
- Pakete: `samba`, `cifs-utils`, `cups`, `python-pip`, `python-cryptography`, `python-pycryptodome`, `libnotify`
- Gültiges **Kerberos-Ticket** des angemeldeten Benutzers (`klist`)
- Root für Installation und `endeavour-gpupdate`

---

## Installation (empfohlen)

Auf dem Client im Firmennetz:

```bash
git clone https://github.com/thelad-dev/endeavour-gpo.git
cd endeavour-gpo
sudo ./scripts/install.sh
```

Das Skript installiert Abhängigkeiten, das Python-Paket, registriert die CSEs,
aktiviert Timer/Socket, richtet Samba `apply group policies = yes` ein und
installiert ein CUPS-`smb`-Backend mit Kerberos-Unterstützung.

Danach (falls nicht schon im Skript gelaufen):

```bash
klist   # Ticket vorhanden?
sudo endeavour-gpupdate --force
```

### Manuell (ohne install.sh)

```bash
sudo pacman -S --needed samba cifs-utils cups python-pip \
  python-cryptography python-pycryptodome libnotify
sudo python3 -m pip install -e . --break-system-packages
sudo endeavour-gpo-register
sudo endeavour-gpupdate --force
```

---

## Alltag

```bash
# Richtlinien erzwingen (User + Kerberos aus SUDO_USER)
sudo endeavour-gpupdate --force

# Ergebnis anzeigen
sudo endeavour-gpupdate --rsop

# Alle aktiven Sitzungen (Timer / Remote)
sudo endeavour-gpupdate --force --all-sessions
```

### Wo liegen die Laufwerke?

```text
~/netzlaufwerke/Q_IT
~/netzlaufwerke/Z_PUBLIC
~/netzlaufwerke/H_ladwein     # aus AD homeDirectory/homeDrive
```

### Drucker

```bash
lpstat -a
lpstat -v
echo "Test" | lp -d endeavour-sophos-buchhaltung
```

CUPS nutzt nach der Installation ein **root-only** `smb`-Backend, das das
Kerberos-Ticket des druckenden Users (`AUTH_UID` → `/tmp/krb5cc_<uid>`) setzt.

### Remote (Admin-PC / DC)

```bash
endeavour-gpupdate-remote nb64
# = ssh nb64 'sudo systemctl start endeavour-gpupdate.service'
```

Socket nur lokal: `127.0.0.1:46327`.

---

## Was `endeavour-gpo-register` macht

1. CSEs in `/var/lib/samba/gpext.conf` (Drive + Printer, ans Ende sortiert)
2. Include `/etc/samba/endeavour-gpo.conf` → `apply group policies = yes`
3. systemd: Timer, Login-Service, Remote-Socket
4. CUPS: Kerberos-fähiges `smb`-Backend
5. Optional: udev-Sleep-Guard am Netzteil (wenn Skript vorhanden)

---

## Architektur

```text
endeavour-gpupdate / samba-gpupdate / winbind
  ├── Endeavour/Preferences/Drives    → mount.cifs + AD-Home
  └── Endeavour/Preferences/Printers  → CUPS SharedPrinter
```

Item-Level-Targeting: `FilterGroup`, `FilterCollection`, `FilterUser`, `FilterRunOnce`.
Andere Filter → Eintrag wird übersprungen (Warnung im Log).

---

## Sicherheit

- Bevorzuge Kerberos; Legacy-`cpassword` wird nur bei Bedarf entschlüsselt (bekannter MS-GPPREF-Schlüssel).
- Credentials-Dateien für Drive-Maps (falls nötig): `~/.cache/endeavour-gpo/credentials/drive-<letter>.cred` (Mode `0600`).
- Remote-Socket nur localhost; echte Remote-Steuerung über SSH.

---

## Entwicklung

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Lizenz

GPL-3.0-or-later (kompatibel zum Samba-`gp_ext`-Framework).
